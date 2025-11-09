from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.app.engine import (
    full_sync_due,
    _description_for_task,
    _status_for_task,
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
