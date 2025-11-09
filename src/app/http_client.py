"""
Worker-aware HTTP helper that falls back to direct js.fetch when available,
otherwise uses the local requests session (for dev CLI usage).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:  # pragma: no cover - only available inside Workers
    import js  # type: ignore
    from js import Headers, Uint8Array  # type: ignore
    from pyodide.ffi import to_js  # type: ignore

    HAS_JS = True
except ImportError:  # pragma: no cover
    js = None  # type: ignore
    Headers = None  # type: ignore
    Uint8Array = None  # type: ignore
    to_js = None  # type: ignore
    HAS_JS = False

_FETCH = None
if HAS_JS:
    try:  # direct import if exposed
        from js import fetch as _direct_fetch  # type: ignore
    except ImportError:
        _direct_fetch = None  # type: ignore
    try:
        from js import globalThis as _global_this  # type: ignore
    except ImportError:
        _global_this = None  # type: ignore
    _FETCH = (
        _direct_fetch  # type: ignore[arg-type]
        or getattr(js, "fetch", None)
        or (getattr(_global_this, "fetch", None) if _global_this is not None else None)
    )

if HAS_JS and _FETCH is None:
    HAS_JS = False

if not HAS_JS:
    import requests


async def http_request(  # pragma: no cover - exercised in Workers
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str | bytes] = None,
) -> Dict[str, Any]:
    if HAS_JS and _FETCH:
        opts = js.Object.new()
        opts.method = method.upper()
        header_obj = Headers.new()
        for key, value in (headers or {}).items():
            header_obj.append(key, value)
        opts.headers = header_obj
        if body is not None:
            payload = body.encode("utf-8") if isinstance(body, str) else body
            opts.body = to_js(payload)
        resp = await _FETCH(url, opts)
        status = int(resp.status)
        header_dict: Dict[str, str] = {}
        entries = resp.headers.entries()
        while True:
            entry = entries.next()
            if bool(entry.done):
                break
            header_dict[str(entry.value[0]).lower()] = str(entry.value[1])
        buffer = await resp.arrayBuffer()
        data_bytes = bytes(Uint8Array.new(buffer).to_py())
        return {"status": status, "headers": header_dict, "body": data_bytes}

    session = requests.Session()
    resp = session.request(method.upper(), url, headers=headers, data=body)
    return {"status": resp.status_code, "headers": dict(resp.headers), "body": resp.content}


async def http_json(  # pragma: no cover - exercised in Workers
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str | bytes] = None,
) -> Dict[str, Any]:
    result = await http_request(url, method=method, headers=headers, body=body)
    import json

    try:
        payload = result["body"].decode("utf-8") if result["body"] else ""
        result["json"] = json.loads(payload) if payload else {}
    except Exception:
        result["json"] = {}
    return result
