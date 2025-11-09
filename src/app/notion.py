import json
from typing import Dict, List, Optional

try:
    from .constants import (
        TITLE_PROPERTY,
        STATUS_PROPERTY,
        DATE_PROPERTY,
        REMINDER_PROPERTY,
        CATEGORY_PROPERTY,
        DESCRIPTION_PROPERTY,
        NOTION_DB_PAGE_SIZE,
        NOTION_DS_PAGE_SIZE,
    )
    from .task import TaskInfo
    from .http_client import http_json
except ImportError:  # pragma: no cover
    from constants import (  # type: ignore
        TITLE_PROPERTY,
        STATUS_PROPERTY,
        DATE_PROPERTY,
        REMINDER_PROPERTY,
        CATEGORY_PROPERTY,
        DESCRIPTION_PROPERTY,
        NOTION_DB_PAGE_SIZE,
        NOTION_DS_PAGE_SIZE,
    )
    from task import TaskInfo  # type: ignore
    from http_client import http_json  # type: ignore


def _use_data_sources(api_version: str) -> bool:
    return api_version >= "2025-09-03"


def _headers(token: str, api_version: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": api_version,
        "Content-Type": "application/json",
    }


async def list_databases(token: str, api_version: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    filter_value = "data_source" if _use_data_sources(api_version) else "database"
    body = {
        "filter": {"property": "object", "value": filter_value},
        "page_size": NOTION_DB_PAGE_SIZE,
    }
    next_cursor: Optional[str] = None
    while True:
        if next_cursor:
            body["start_cursor"] = next_cursor
        response = await http_json(
            "https://api.notion.com/v1/search",
            method="POST",
            headers=_headers(token, api_version),
            body=json.dumps(body),
        )
        data = response.get("json") or {}
        for db in data.get("results", []):
            title = ""
            title_arr = db.get("title", [])
            if not title_arr and isinstance(db.get("data_source"), dict):
                title_arr = db["data_source"].get("title", [])
            if title_arr:
                title = title_arr[0].get("plain_text") or title_arr[0].get("text", {}).get("content", "")
            db_id = db.get("id") or ((db.get("data_source") or {}).get("id"))
            if not db_id:
                continue
            results.append({"id": db_id, "title": title or "Untitled"})
        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            print("[notion] missing next_cursor in search response despite has_more; stopping pagination")
            break
    return results


async def get_database(token: str, api_version: str, database_id: str) -> Dict:
    if _use_data_sources(api_version):
        url = f"https://api.notion.com/v1/data_sources/{database_id}"
    else:
        url = f"https://api.notion.com/v1/databases/{database_id}"
    response = await http_json(url, headers=_headers(token, api_version))
    return response.get("json") or {}


async def get_database_title(token: str, api_version: str, database_id: str) -> str:
    database = await get_database(token, api_version, database_id)
    if _use_data_sources(api_version):
        title_entries = (database.get("title") or [])
    else:
        title_entries = database.get("title") or []
    for entry in title_entries:
        text = entry.get("plain_text") or entry.get("text", {}).get("content")
        if text:
            return str(text)
    name = database.get("name")
    if isinstance(name, str) and name:
        return name
    return database.get("id") or "Untitled"

async def get_database_properties(token: str, api_version: str, database_id: str) -> Dict[str, dict]:
    data = await get_database(token, api_version, database_id)
    if data.get("object") == "error":
        return {}
    return data.get("properties") or {}


async def query_database_pages(token: str, api_version: str, database_id: str) -> List[Dict]:
    pages: List[Dict] = []
    next_cursor: Optional[str] = None
    while True:
        body = {
            "page_size": NOTION_DB_PAGE_SIZE,
            "filter_properties": [
                TITLE_PROPERTY,
                STATUS_PROPERTY,
                DATE_PROPERTY,
                REMINDER_PROPERTY,
                CATEGORY_PROPERTY,
                DESCRIPTION_PROPERTY,
            ],
        }
        if _use_data_sources(api_version):
            body.pop("filter_properties", None)
            body["page_size"] = NOTION_DS_PAGE_SIZE
        if next_cursor:
            body["start_cursor"] = next_cursor
        if _use_data_sources(api_version):
            url = f"https://api.notion.com/v1/data_sources/{database_id}/query"
        else:
            url = f"https://api.notion.com/v1/databases/{database_id}/query"
        response = await http_json(
            url,
            method="POST",
            headers=_headers(token, api_version),
            body=json.dumps(body),
        )
        data = response.get("json") or {}
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            print("[notion] missing next_cursor in database query despite has_more; stopping pagination")
            break
    return pages


async def get_page(token: str, api_version: str, page_id: str) -> Dict:
    response = await http_json(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_headers(token, api_version),
    )
    return response.get("json") or {}


def _extract_title_from_prop(prop: Dict) -> str:
    if not isinstance(prop, dict) or prop.get("type") != "title":
        return ""
    text_items = prop.get("title") or []
    parts: List[str] = []
    for item in text_items:
        if not isinstance(item, dict):
            continue
        text = item.get("plain_text") or item.get("text", {}).get("content")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def parse_page_to_task(page: Dict) -> TaskInfo:
    props = page.get("properties", {})
    title_prop = props.get(TITLE_PROPERTY, {})
    title = _extract_title_from_prop(title_prop)
    if not title:
        for value in props.values():
            if value is title_prop:
                continue
            title = _extract_title_from_prop(value)
            if title:
                break
    if not title:
        title = page.get("id") or "Untitled"
    status_prop = props.get(STATUS_PROPERTY) or {}
    status_data = status_prop.get("status") or {}
    status = status_data.get("name")
    date_prop = props.get(DATE_PROPERTY) or {}
    date_value = date_prop.get("date") or {}
    start = date_value.get("start")
    end = date_value.get("end")
    reminder_prop = props.get(REMINDER_PROPERTY) or {}
    reminder_value = reminder_prop.get("date") or {}
    reminder = reminder_value.get("start")
    category_prop = props.get(CATEGORY_PROPERTY) or {}
    category = None
    if isinstance(category_prop, dict) and category_prop.get("type") == "select":
        select_data = category_prop.get("select") or {}
        category = select_data.get("name")
    description_prop = props.get(DESCRIPTION_PROPERTY) or {}
    description = None
    if isinstance(description_prop, dict) and description_prop.get("type") == "rich_text" and description_prop.get("rich_text"):
        description = description_prop["rich_text"][0].get("plain_text", "")

    return TaskInfo(
        notion_id=page.get("id"),
        title=title,
        status=status,
        start_date=start,
        end_date=end,
        reminder=reminder,
        category=category,
        description=description,
        url=page.get("url"),
    )
