from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NOTION_VERSION = "2025-09-03"


@dataclass(slots=True)
class Bindings:
    """Resolved Worker bindings with consistent attribute names."""

    state: Any
    apple_id: str
    apple_app_password: str
    notion_token: str
    admin_token: str = ""

    @classmethod
    def from_worker_env(cls, env: Any) -> "Bindings":
        """Create bindings from the Workers runtime env object."""
        return cls(
            state=getattr(env, "STATE", None),
            apple_id=getattr(env, "APPLE_ID", "") or "",
            apple_app_password=getattr(env, "APPLE_APP_PASSWORD", "") or "",
            notion_token=getattr(env, "NOTION_TOKEN", "") or "",
            admin_token=getattr(env, "ADMIN_TOKEN", "") or "",
        )


def get_bindings(env: Any) -> Bindings:
    return Bindings.from_worker_env(env)
