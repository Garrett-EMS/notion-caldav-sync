from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.app.engine import (
    full_sync_due,
    _description_for_task,
    _status_for_task,
    handle_webhook_tasks,
)  # type: ignore
from src.app.task import TaskInfo


def test_full_sync_due_handles_missing_and_recent_values():
    assert full_sync_due({})  # no record, should run
    now = datetime.now(timezone.utc)
    settings_recent = {
        "last_full_sync": now.isoformat(),
        "full_sync_interval_minutes": 60,
    }
    assert not full_sync_due(settings_recent)
    settings_old = {
        "last_full_sync": (now - timedelta(minutes=61)).isoformat(),
        "full_sync_interval_minutes": 60,
    }
    assert full_sync_due(settings_old)


def test_description_for_task_includes_datasource_and_optional_fields():
    task = TaskInfo(
        notion_id="abc",
        title="Test",
        status="Todo",
        database_name="Inbox",
        category="Work",
        description="Do something",
    )
    text = _description_for_task(task)
    assert "Source: Inbox" in text
    assert "Category: Work" in text
    assert text.endswith("Do something")


def test_status_for_task_marks_overdue_when_due_passed():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    task = TaskInfo(
        notion_id="abc",
        title="Late",
        status="In progress",
        start_date=past,
    )
    assert _status_for_task(task) == "Overdue"


def test_status_for_task_respects_completed_states():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    task = TaskInfo(
        notion_id="abc",
        title="Done",
        status="Completed",
        start_date=past,
    )
    assert _status_for_task(task) == "Completed"


class _DummyBindings:
    def __init__(self):
        self.state = object()
        self.apple_id = "apple@example.com"
        self.apple_app_password = "secret"
        self.notion_token = "token"


@pytest.mark.asyncio
async def test_handle_webhook_tasks_deletes_when_page_missing(monkeypatch: pytest.MonkeyPatch):
    deleted: list[str] = []

    async def _fake_calendar_ensure(_):
        return {"calendar_href": "https://calendar", "calendar_color": "#fff"}

    async def _fake_get_page(*_args, **_kwargs):
        return {"object": "error"}

    async def _fake_delete(_bindings, calendar_href, notion_id):
        deleted.append(notion_id)
        assert calendar_href == "https://calendar"

    monkeypatch.setattr("src.app.engine.calendar_ensure", _fake_calendar_ensure)
    monkeypatch.setattr("src.app.engine.get_page", _fake_get_page)
    monkeypatch.setattr("src.app.engine._delete_task_event", _fake_delete)

    bindings = _DummyBindings()
    page_id = "1234abcd-1234-abcd-1234-abcd1234abcd"
    await handle_webhook_tasks(bindings, [page_id])

    assert deleted == [page_id]


@pytest.mark.asyncio
async def test_handle_webhook_tasks_deletes_when_parent_missing(monkeypatch: pytest.MonkeyPatch):
    deleted: list[str] = []

    async def _fake_calendar_ensure(_):
        return {"calendar_href": "https://calendar", "calendar_color": "#fff"}

    async def _fake_get_page(*_args, **_kwargs):
        return {"id": "abcd1234-abcd-1234-abcd-1234abcd1234", "parent": {}}

    async def _fake_delete(_bindings, calendar_href, notion_id):
        deleted.append(notion_id)
        assert calendar_href == "https://calendar"

    monkeypatch.setattr("src.app.engine.calendar_ensure", _fake_calendar_ensure)
    monkeypatch.setattr("src.app.engine.get_page", _fake_get_page)
    monkeypatch.setattr("src.app.engine._delete_task_event", _fake_delete)

    bindings = _DummyBindings()
    page_id = "abcd1234-abcd-1234-abcd-1234abcd1234"
    await handle_webhook_tasks(bindings, [page_id])

    assert deleted == [page_id]
