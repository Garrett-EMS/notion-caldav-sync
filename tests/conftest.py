"""Global pytest fixtures for the integration test suite."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pytest
from dotenv import load_dotenv

from src.app.config import NOTION_VERSION
from src.app.notion import list_databases


# --- Runtime shim ---------------------------------------------------------


class _JSResponse:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.status = response.status_code
        self.headers = response.headers

    async def json(self) -> Any:
        return self._response.json()

    async def text(self) -> str:
        return self._response.text


async def _js_fetch(url: str, options: Optional[Dict[str, Any]] = None) -> _JSResponse:
    opts: Dict[str, Any] = options or {}
    method = opts.get("method", "GET")
    headers = opts.get("headers") or {}
    content = opts.get("body")
    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.request(method, url, headers=headers, content=content)
    return _JSResponse(response)


class _JSONShim:
    @staticmethod
    def stringify(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False)

    @staticmethod
    def parse(data: str) -> Any:
        return json.loads(data)


class _WorkersResponse:
    def __init__(
        self,
        body: str = "",
        init: Optional[Dict[str, Any]] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        status: int = 200,
    ) -> None:
        init_status = init.get("status") if isinstance(init, dict) else None
        init_headers = init.get("headers") if isinstance(init, dict) else None
        self.status = init_status if init_status is not None else status
        self.headers = init_headers if init_headers is not None else headers or {}
        self.body = body


class _WorkersRequest:
    def __init__(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, body: str = "") -> None:
        self.url = url
        self.method = method
        self.headers = headers or {}
        self._body = body

    async def text(self) -> str:
        return self._body


def _install_runtime_shims() -> None:
    if "js" not in sys.modules:
        js_mod = types.ModuleType("js")
        js_mod.fetch = _js_fetch
        js_mod.JSON = _JSONShim
        sys.modules["js"] = js_mod

    if "workers" not in sys.modules:
        workers_mod = types.ModuleType("workers")
        workers_mod.Response = _WorkersResponse
        workers_mod.Request = _WorkersRequest
        workers_mod.WorkerEntrypoint = type("WorkerEntrypoint", (), {})
        sys.modules["workers"] = workers_mod


_install_runtime_shims()


# --- Settings helpers -----------------------------------------------------


REQUIRED_ENV_KEYS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_STATE_NAMESPACE",
    "CLOUDFLARE_API_TOKEN",
    "NOTION_TOKEN",
    "APPLE_ID",
    "APPLE_APP_PASSWORD",
)


@dataclass(frozen=True)
class Settings:
    account_id: str
    state_namespace: str
    api_token: str
    notion_token: str
    notion_version: str
    apple_id: str
    apple_app_password: str

    @property
    def state_base_url(self) -> str:
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/storage/kv/namespaces/{self.state_namespace}/values"
        )


def _resolve_env_file(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        return Path(explicit).expanduser().resolve()
    default_path = Path.cwd() / ".env"
    return default_path if default_path.exists() else None


def _ensure_loaded(path: Optional[Path]) -> None:
    if path is None:
        load_dotenv()
        return
    load_dotenv(path)


def _require(values: dict, key: str) -> str:
    value = values.get(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


@lru_cache(maxsize=1)
def load_settings(explicit_env_file: Optional[str] = None) -> Settings:
    env_path = _resolve_env_file(explicit_env_file or os.getenv("TESTS_ENV_FILE"))
    _ensure_loaded(env_path)

    environ = dict(os.environ)
    for key in REQUIRED_ENV_KEYS:
        _require(environ, key)

    notion_version = environ.get("NOTION_API_VERSION", NOTION_VERSION)

    return Settings(
        account_id=environ["CLOUDFLARE_ACCOUNT_ID"],
        state_namespace=environ["CLOUDFLARE_STATE_NAMESPACE"],
        api_token=environ["CLOUDFLARE_API_TOKEN"],
        notion_token=environ["NOTION_TOKEN"],
        notion_version=notion_version,
        apple_id=environ["APPLE_ID"],
        apple_app_password=environ["APPLE_APP_PASSWORD"],
    )


# --- KV helpers -----------------------------------------------------------


class KVClient:
    def __init__(self, base_url: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "text/plain",
        }

    async def get(self, key: str) -> Optional[str]:
        url = f"{self._base_url}/{key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(url, headers=self._headers)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise RuntimeError(f"KV get failed ({response.status_code}) for {key}")
        return response.text

    async def put(self, key: str, value: str, options: Optional[dict] = None) -> None:
        params = {}
        if options and options.get("expirationTtl"):
            params["expiration_ttl"] = str(int(options["expirationTtl"]))
        url = f"{self._base_url}/{key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.put(url, headers=self._headers, params=params, content=value)
        if response.status_code >= 400:
            raise RuntimeError(f"KV put failed ({response.status_code}) for {key}")

    async def delete(self, key: str) -> None:
        url = f"{self._base_url}/{key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.delete(url, headers=self._headers)
        if response.status_code >= 400 and response.status_code != 404:
            raise RuntimeError(f"KV delete failed ({response.status_code}) for {key}")


@dataclass
class TestEnv:
    STATE: KVClient
    APPLE_ID: str
    APPLE_APP_PASSWORD: str
    NOTION_TOKEN: str
    NOTION_VERSION: str


TestEnv.__test__ = False


def build_env(settings: Settings) -> TestEnv:
    state_client = KVClient(settings.state_base_url, settings.api_token)
    return TestEnv(
        STATE=state_client,
        APPLE_ID=settings.apple_id,
        APPLE_APP_PASSWORD=settings.apple_app_password,
        NOTION_TOKEN=settings.notion_token,
        NOTION_VERSION=settings.notion_version,
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--env-file",
        action="store",
        default=None,
        help="Path to the .env file containing credentials for live integration tests.",
    )


@pytest.fixture(scope="session")
def settings(pytestconfig: pytest.Config) -> Settings:
    env_file = pytestconfig.getoption("--env-file")
    return load_settings(env_file)


@pytest.fixture(scope="session")
def env(settings: Settings) -> TestEnv:
    return build_env(settings)


@pytest.fixture(scope="session")
def notion_version(settings: Settings) -> str:
    return settings.notion_version


@pytest.fixture(scope="session")
def task_database_ids(env: TestEnv, notion_version: str) -> List[str]:
    async def _resolve() -> List[str]:
        databases = await list_databases(env.NOTION_TOKEN, notion_version)
        unique_ids: List[str] = []
        for db in databases:
            db_id = db.get("id")
            if db_id and db_id not in unique_ids:
                unique_ids.append(db_id)
        return unique_ids

    database_ids = asyncio.run(_resolve())
    if not database_ids:
        raise RuntimeError(
            "Failed to discover any Notion task databases via the /v1/search endpoint. "
            "Ensure the integration has access to at least one database configured for tasks."
        )
    return database_ids


@pytest.fixture(scope="session")
def primary_database_id(task_database_ids: List[str]) -> str:
    return task_database_ids[0]
