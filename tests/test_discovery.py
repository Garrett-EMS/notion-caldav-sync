"""CalDAV discovery regression tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.app import engine
from src.app.constants import CALDAV_ORIGIN
from src.app.discovery import discover_calendar_home, discover_principal, list_calendars
from src.app.config import get_bindings

if TYPE_CHECKING:
    from tests.conftest import TestEnv


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_principal_and_home(env: TestEnv) -> None:
    principal = await discover_principal(CALDAV_ORIGIN, env.APPLE_ID, env.APPLE_APP_PASSWORD)
    assert principal
    home = await discover_calendar_home(CALDAV_ORIGIN, principal, env.APPLE_ID, env.APPLE_APP_PASSWORD)
    assert home


@pytest.mark.asyncio
async def test_list_calendars(env: TestEnv) -> None:
    principal = await discover_principal(CALDAV_ORIGIN, env.APPLE_ID, env.APPLE_APP_PASSWORD)
    home = await discover_calendar_home(CALDAV_ORIGIN, principal, env.APPLE_ID, env.APPLE_APP_PASSWORD)
    calendars = await list_calendars(CALDAV_ORIGIN, home, env.APPLE_ID, env.APPLE_APP_PASSWORD)
    display_names = [item.get("displayName") for item in calendars]
    assert calendars
    if not any(name and "Notion" in name for name in display_names):
        await engine.ensure_calendar(get_bindings(env))
        calendars = await list_calendars(CALDAV_ORIGIN, home, env.APPLE_ID, env.APPLE_APP_PASSWORD)
        display_names = [item.get("displayName") for item in calendars]
    assert any(name and "Notion" in name for name in display_names)
