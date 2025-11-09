import hashlib
import hmac
import json
import uuid
from typing import Any, Iterable, List, Optional

from workers import Response

try:
    from .config import get_bindings
    from .engine import handle_webhook_tasks
    from .stores import load_webhook_token, persist_webhook_token
except ImportError:
    from config import get_bindings  # type: ignore
    from engine import handle_webhook_tasks  # type: ignore
    from stores import load_webhook_token, persist_webhook_token  # type: ignore


_PAGE_ID_KEYS = {"page_id", "pageId"}
_LOG_CHAR_LIMIT = 2000


def _normalize_page_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    normalized = candidate.replace("-", "")
    if len(normalized) != 32:
        return None
    try:
        parsed = uuid.UUID(normalized)
    except ValueError:
        return None
    return str(parsed)


def _collect_page_ids(payload: Any) -> List[str]:
    found: List[str] = []

    def _append(candidate: Any) -> None:
        normalized = _normalize_page_id(candidate)
        if normalized:
            found.append(normalized)

    def _walk(value: Any, parent_key: Optional[str] = None) -> None:
        if isinstance(value, dict):
            object_hint = str(value.get("object") or value.get("type") or "").lower()
            if object_hint == "page" or parent_key == "page":
                _append(value.get("id") or value.get("page_id"))
            for key, nested in value.items():
                if key in _PAGE_ID_KEYS:
                    _append(nested)
                    continue
                if key == "parent" and isinstance(nested, dict):
                    _append(nested.get("page_id"))
                if key == "value" and isinstance(nested, dict):
                    _walk(nested, key)
                    continue
                if key in {"payload", "data", "after", "before"}:
                    _walk(nested, key)
                    continue
                if isinstance(nested, (dict, list)):
                    _walk(nested, key)
        elif isinstance(value, list):
            for item in value:
                _walk(item, parent_key)

    _walk(payload)
    ordered: List[str] = []
    seen = set()
    for pid in found:
        if pid in seen:
            continue
        seen.add(pid)
        ordered.append(pid)
    return ordered


def _format_payload_for_log(raw: str, data: Any) -> str:
    if isinstance(data, (dict, list)):
        try:
            body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            body = raw or ""
    else:
        body = raw or ""
    snippet = body.strip()
    if not snippet and raw:
        snippet = raw.strip()
    if len(snippet) <= _LOG_CHAR_LIMIT:
        return snippet or "<empty>"
    trimmed = snippet[:_LOG_CHAR_LIMIT]
    remainder = len(snippet) - _LOG_CHAR_LIMIT
    return f"{trimmed}... (+{remainder} chars truncated)"


def _log_payload(raw: str, data: Any, page_ids: Iterable[str]) -> None:
    snapshot = _format_payload_for_log(raw, data)
    pid_list = list(page_ids)
    print(f"[Webhook] payload: {snapshot} :: page_ids={pid_list or []}")


async def handle(request, env, ctx=None):
    """
    Handle Notion webhook requests.
    ctx parameter is optional for compatibility with Python Workers API.
    """
    bindings = get_bindings(env)
    raw = await request.text()

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = None

    verification_token = None
    if isinstance(data, dict):
        verification_token = data.get("verification_token")

    if verification_token:
        verification_token = str(verification_token).strip()
        if not verification_token:
            return Response("Invalid verification_token", status=400)
        await persist_webhook_token(bindings.state, verification_token)
        print("[Webhook] Stored verification token from Notion")
        response_body = json.dumps({"verification_token": verification_token})
        return Response(response_body, headers={"Content-Type": "application/json"})

    if data is None:
        print("[Webhook] ERROR: Invalid JSON")
        return Response("Invalid JSON", status=400)

    stored_token = await load_webhook_token(bindings.state)
    if not stored_token:
        seed = getattr(env, "WEBHOOK_VERIFICATION_TOKEN", "") or ""
        seed = seed.strip()
        if seed:
            await persist_webhook_token(bindings.state, seed)
            stored_token = seed

    if not stored_token:
        return Response("Unauthorized - Missing stored verification token", status=401)

    sig = request.headers.get('X-Notion-Signature')
    if not sig:
        return Response("Unauthorized - No signature", status=401)

    calc = 'sha256=' + hmac.new(stored_token.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, sig):
        return Response("Unauthorized - Invalid signature", status=401)
    
    page_ids: List[str] = _collect_page_ids(data)
    _log_payload(raw, data, page_ids)
    await handle_webhook_tasks(bindings, page_ids)
    response_body = json.dumps({"ok": True, "updated": page_ids})
    return Response(response_body, headers={"Content-Type": "application/json"})
