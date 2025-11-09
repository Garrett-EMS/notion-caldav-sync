import pytest

from src.app import notion
from src.app.notion import extract_database_title, get_database_title


def test_extract_database_title_prefers_rich_text():
    meta = {
        "title": [
            {
                "plain_text": "Project Tracker",
                "text": {"content": "ignored"},
            }
        ]
    }

    assert extract_database_title(meta) == "Project Tracker"


def test_extract_database_title_handles_name_arrays():
    meta = {
        "name": [
            {"plain_text": "Inbox"}
        ]
    }

    assert extract_database_title(meta) == "Inbox"


def test_extract_database_title_uses_data_source_display_name():
    meta = {
        "data_source": {
            "displayName": "Notion Tasks",
        }
    }

    assert extract_database_title(meta) == "Notion Tasks"


def test_extract_database_title_returns_none_when_absent():
    assert extract_database_title({}) is None


@pytest.mark.asyncio
async def test_get_database_title_uses_data_source_metadata(monkeypatch: pytest.MonkeyPatch):
    async def _fake_fetch(*_args, **_kwargs):
        return {
            "title": [
                {"plain_text": "Real Tasks"}
            ]
        }

    monkeypatch.setattr(notion, "_fetch_data_source_metadata", _fake_fetch)

    title = await get_database_title("token", "2025-09-03", "db1")

    assert title == "Real Tasks"


@pytest.mark.asyncio
async def test_get_database_title_raises_when_data_source_missing(monkeypatch: pytest.MonkeyPatch):
    async def _fake_fetch(*_args, **_kwargs):
        return None

    monkeypatch.setattr(notion, "_fetch_data_source_metadata", _fake_fetch)

    with pytest.raises(RuntimeError):
        await get_database_title("token", "2025-09-03", "db1")
