"""Minimal WebDAV helper utilities for both Workers and local dev."""

from __future__ import annotations

import asyncio
import base64
from typing import Dict, Optional, Tuple

try:  # pragma: no cover - only available inside the Workers runtime
    import js  # type: ignore
    from js import Headers, Uint8Array  # type: ignore
    from pyodide.ffi import JsException, to_js  # type: ignore

    JS_RUNTIME = True
except ImportError:  # pragma: no cover
    js = None  # type: ignore
    Headers = None  # type: ignore
    Uint8Array = None  # type: ignore
    JsException = Exception  # type: ignore
    to_js = None  # type: ignore
    JS_RUNTIME = False

_FETCH = None
if JS_RUNTIME:
    try:
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

if JS_RUNTIME and _FETCH is None:
    JS_RUNTIME = False

if JS_RUNTIME:  # pragma: no cover
    requests = None  # type: ignore
else:
    import requests  # type: ignore

HAS_NATIVE_WEBDAV = JS_RUNTIME


def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


async def http_request(
    method: str,
    url: str,
    username: str,
    password: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes | str] = None,
    expect_body: bool = True,
) -> Tuple[int, Dict[str, str], bytes]:
    """Execute an HTTP/WebDAV request using fetch (Workers) or requests (local)."""
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)
    headers.setdefault("Authorization", _basic_auth_header(username, password))

    method = method.upper()

    if JS_RUNTIME and _FETCH:
        options = js.Object.new()
        options.method = method
        header_obj = Headers.new()
        for key, value in headers.items():
            header_obj.append(key, value)
        options.headers = header_obj
        if body is not None:
            payload = body.encode("utf-8") if isinstance(body, str) else body
            options.body = to_js(payload)

        try:
            response = await _FETCH(url, options)
        except JsException as exc:  # pragma: no cover - surfaced at runtime
            raise RuntimeError(f"fetch failed: {exc}") from None

        status = int(response.status)
        header_dict: Dict[str, str] = {}
        header_entries = response.headers.entries()
        while True:
            entry = header_entries.next()
            if bool(entry.done):
                break
            key = str(entry.value[0]).lower()
            header_dict[key] = str(entry.value[1])

        if not expect_body:
            return status, header_dict, b""

        buffer = await response.arrayBuffer()
        body_bytes = bytes(Uint8Array.new(buffer).to_py())
        return status, header_dict, body_bytes

    def _request_via_requests() -> Tuple[int, Dict[str, str], bytes]:
        data = body.encode("utf-8") if isinstance(body, str) else body
        resp = requests.request(method, url, headers=headers, data=data)
        header_dict = {k.lower(): v for k, v in resp.headers.items()}
        if not expect_body:
            return resp.status_code, header_dict, b""
        return resp.status_code, header_dict, resp.content

    return await asyncio.to_thread(_request_via_requests)


async def http_request_xml(
    method: str,
    url: str,
    username: str,
    password: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    expect_body: bool = True,
) -> Tuple[int, Dict[str, str], str]:
    status, hdrs, payload = await http_request(
        method,
        url,
        username,
        password,
        headers=headers,
        body=body,
        expect_body=expect_body,
    )
    text = payload.decode("utf-8") if payload else ""
    return status, hdrs, text


def get_header(headers: Dict[str, str], name: str) -> Optional[str]:
    key = name.lower()
    return headers.get(key)
