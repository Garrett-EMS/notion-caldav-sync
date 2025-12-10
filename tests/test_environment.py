"""Basic health checks for environment configuration used in integration tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
import tomllib

if TYPE_CHECKING:
    from tests.conftest import Settings


if not os.getenv("CLOUDFLARE_STATE_NAMESPACE"):
    pytest.skip("Integration environment not configured", allow_module_level=True)

pytestmark = pytest.mark.integration


def _state_namespace_from_wrangler() -> str | None:
    wrangler_path = Path.cwd() / "wrangler.toml"
    if not wrangler_path.exists():
        return None
    try:
        config = tomllib.loads(wrangler_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    for entry in config.get("kv_namespaces") or []:
        if entry.get("binding") != "STATE":
            continue
        namespace_id = entry.get("id")
        if isinstance(namespace_id, str) and not namespace_id.strip().startswith("${"):
            return namespace_id.strip()
    return None


@pytest.mark.asyncio
async def test_clear_all_workers_kv(settings: Settings) -> None:
    account_id = settings.account_id
    api_token = settings.api_token
    candidate_state_ids = [settings.state_namespace]
    wrangler_namespace_id = _state_namespace_from_wrangler()
    if wrangler_namespace_id and wrangler_namespace_id not in candidate_state_ids:
        candidate_state_ids.append(wrangler_namespace_id)

    base_prefix = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/storage/kv/namespaces"
    )
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(60.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for namespace_id in candidate_state_ids:
            namespace_url = f"{base_prefix}/{namespace_id}"
            collected_keys: list[str] = []
            cursor: str | None = None
            missing_namespace = False

            while True:
                params = {"limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                response = await client.get(f"{namespace_url}/keys", headers=headers, params=params)
                if response.status_code == 404:
                    # Namespace id likely stale; try next candidate.
                    missing_namespace = True
                    break
                response.raise_for_status()

                payload = response.json()
                result = payload.get("result") or []
                collected_keys.extend(entry["name"] for entry in result)

                result_info = payload.get("result_info") or {}
                cursor = result_info.get("cursor")
                if not cursor:
                    break

            if missing_namespace:
                continue

            for offset in range(0, len(collected_keys), 1000):
                chunk = collected_keys[offset : offset + 1000]
                for key in chunk:
                    delete_response = await client.delete(
                        f"{namespace_url}/values/{key}", headers=headers
                    )
                    if delete_response.status_code not in (200, 204, 404):
                        delete_response.raise_for_status()

            verify_response = await client.get(f"{namespace_url}/keys", headers=headers)
            verify_response.raise_for_status()
            remaining = verify_response.json().get("result") or []
            assert not remaining, "STATE namespace still has keys after purge"
            return

    pytest.fail(
        "STATE namespace not found in the account; update CLOUDFLARE_STATE_NAMESPACE "
        "to match wrangler.toml or rerun deploy.sh to recreate it."
    )


def test_settings_have_all_required_fields(settings: Settings) -> None:
    assert settings.account_id
    assert settings.state_namespace
    assert settings.api_token
    assert settings.notion_token
    assert settings.apple_id
    assert settings.apple_app_password
