"""Live tests for Notion REST helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.app.notion import list_databases, query_database_pages

if TYPE_CHECKING:
    from tests.conftest import TestEnv


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_list_databases_cover_task_sources(env: TestEnv, notion_version: str, task_database_ids: list[str]) -> None:
    databases = await list_databases(env.NOTION_TOKEN, notion_version)
    available_ids = {db["id"] for db in databases if db.get("id")}
    missing = [db_id for db_id in task_database_ids if db_id not in available_ids]
    assert not missing, f"Underlying databases not discoverable via search: {missing}"


@pytest.mark.asyncio
async def test_query_database_pages_returns_results(env: TestEnv, notion_version: str, primary_database_id: str) -> None:
    pages = await query_database_pages(env.NOTION_TOKEN, notion_version, primary_database_id)
    assert isinstance(pages, list)


def test_resolved_task_databases(task_database_ids: list[str]) -> None:
    assert task_database_ids
