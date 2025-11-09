"""Logging helper that maps to Cloudflare's console when available."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - only available inside Workers runtime
    from js import console  # type: ignore
except ImportError:  # pragma: no cover
    console = None  # type: ignore


def log(message: Any) -> None:
    text = str(message)
    if console is not None:
        console.log(text)
    else:
        print(text, flush=True)
