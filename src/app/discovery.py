"""CalDAV discovery utilities powered by the shared WebDAV helper."""

from __future__ import annotations

from typing import Dict, List
from urllib.parse import urljoin
from xml.sax.saxutils import escape as xml_escape
from uuid import uuid4

try:  # pragma: no cover - lxml unavailable inside Workers
    from lxml import etree  # type: ignore
except ImportError:  # pragma: no cover
    from xml.etree import ElementTree as etree  # type: ignore

try:
    from .webdav import http_request, http_request_xml
except ImportError:  # pragma: no cover
    from webdav import http_request, http_request_xml  # type: ignore

_NS = {
    "d": "DAV:",
    "c": "urn:ietf:params:xml:ns:caldav",
    "cs": "http://calendarserver.org/ns/",
}


async def discover_principal(
    caldav_origin: str, apple_id: str, apple_app_password: str
) -> str:
    body = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<d:propfind xmlns:d=\"DAV:\">"
        "<d:prop><d:current-user-principal/></d:prop>"
        "</d:propfind>"
    )
    headers = {"Depth": "0", "Content-Type": "application/xml; charset=utf-8"}
    status, _, xml_payload = await http_request_xml(
        "PROPFIND",
        caldav_origin,
        apple_id,
        apple_app_password,
        headers=headers,
        body=body,
    )
    if status >= 400:
        raise ValueError(f"Failed to discover principal (status {status})")
    root = etree.fromstring(xml_payload.encode("utf-8"))
    href_node = root.find('.//d:current-user-principal/d:href', namespaces=_NS)
    if href_node is None or not href_node.text:
        raise ValueError("current-user-principal not returned")
    return urljoin(caldav_origin, href_node.text)


async def discover_calendar_home(
    origin: str, principal_href: str, apple_id: str, apple_app_password: str
) -> str:
    principal_url = principal_href or origin
    body = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<d:propfind xmlns:d=\"DAV:\" xmlns:c=\"urn:ietf:params:xml:ns:caldav\">"
        "<d:prop><c:calendar-home-set/></d:prop>"
        "</d:propfind>"
    )
    headers = {"Depth": "0", "Content-Type": "application/xml; charset=utf-8"}
    status, _, xml_payload = await http_request_xml(
        "PROPFIND",
        principal_url,
        apple_id,
        apple_app_password,
        headers=headers,
        body=body,
    )
    if status >= 400:
        raise ValueError(f"Failed to discover calendar home (status {status})")
    root = etree.fromstring(xml_payload.encode("utf-8"))
    home_href = root.find('.//c:calendar-home-set/d:href', namespaces=_NS)
    if home_href is None or not home_href.text:
        raise ValueError("calendar-home-set missing in response")
    return urljoin(origin, home_href.text)


async def list_calendars(
    origin: str, home_set_url: str, apple_id: str, apple_app_password: str
) -> List[Dict[str, str]]:
    target = home_set_url or origin
    body = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<d:propfind xmlns:d=\"DAV:\" xmlns:cs=\"http://calendarserver.org/ns/\" xmlns:c=\"urn:ietf:params:xml:ns:caldav\">"
        "<d:prop>"
        "<d:displayname/><cs:getctag/><d:resourcetype/>"
        "</d:prop>"
        "</d:propfind>"
    )
    headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
    status, _, xml_payload = await http_request_xml(
        "PROPFIND",
        target,
        apple_id,
        apple_app_password,
        headers=headers,
        body=body,
    )
    if status >= 400:
        raise ValueError(f"Failed to list calendars (status {status})")
    root = etree.fromstring(xml_payload.encode("utf-8"))
    calendars: List[Dict[str, str]] = []
    for resp in root.findall("d:response", namespaces=_NS):
        href_node = resp.find("d:href", namespaces=_NS)
        if href_node is None or not href_node.text:
            continue
        props = resp.find("d:propstat/d:prop", namespaces=_NS)
        if props is None:
            continue
        resource = props.find("d:resourcetype", namespaces=_NS)
        if resource is None or resource.find("c:calendar", namespaces=_NS) is None:
            continue
        display_node = props.find("d:displayname", namespaces=_NS)
        ctag_node = props.find("cs:getctag", namespaces=_NS)
        href = urljoin(target, href_node.text)
        if home_set_url and not href.startswith(home_set_url.rstrip("/")):
            continue
        calendars.append(
            {
                "id": href.rstrip("/").split("/")[-1],
                "displayName": display_node.text if display_node is not None else "",
                "href": href,
                "ctag": ctag_node.text if ctag_node is not None else None,
            }
        )
    return calendars


async def mkcalendar(
    origin: str, home_set_url: str, name: str, apple_id: str, apple_app_password: str
) -> str:
    base = home_set_url or origin
    base = base.rstrip("/") + "/"
    slug_raw = name.lower().replace(" ", "-").replace("/", "-")
    slug_base = (slug_raw or "calendar").rstrip("/")
    if slug_base.endswith(".calendar"):
        slug_base = slug_base[: -len(".calendar")]
    if not slug_base:
        slug_base = "calendar"
    primary_id = f"{slug_base}.calendar"
    secondary_id = f"{slug_base}-{uuid4().hex}.calendar"
    safe_name = xml_escape(name)
    mkcalendar_body = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<c:mkcalendar xmlns:d=\"DAV:\" xmlns:c=\"urn:ietf:params:xml:ns:caldav\">"
        f"<d:set><d:prop><d:displayname>{safe_name}</d:displayname></d:prop></d:set>"
        "</c:mkcalendar>"
    )
    headers = {"Content-Type": "application/xml; charset=utf-8"}
    candidates = [primary_id, secondary_id]

    last_status = None
    for cal_id in candidates:
        target = urljoin(base, cal_id.rstrip("/") + "/")
        try:
            status, _, _ = await http_request(
                "MKCALENDAR",
                target,
                apple_id,
                apple_app_password,
                headers=headers,
                body=mkcalendar_body,
            )
        except RuntimeError as exc:
            if "Invalid HTTP method string" not in str(exc):
                raise
            mkcol_body = (
                "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                "<d:mkcol xmlns:d=\"DAV:\" xmlns:c=\"urn:ietf:params:xml:ns:caldav\">"
                "<d:set><d:prop>"
                "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                f"<d:displayname>{safe_name}</d:displayname>"
                "</d:prop></d:set>"
                "</d:mkcol>"
            )
            status, _, _ = await http_request(
                "MKCOL",
                target,
                apple_id,
                apple_app_password,
                headers=headers,
                body=mkcol_body,
            )
        if status in (200, 201):
            return target
        last_status = status

    raise ValueError(f"Failed to create calendar (status {last_status})")
