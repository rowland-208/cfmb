import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import urllib3
from bs4 import BeautifulSoup


_DEFAULT_TIMEOUT = 15
_ET = ZoneInfo("America/New_York")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_meetup_markdown(meetup_url: str, event_count: int = 0) -> str:
    """Returns markdown for upcoming events. `event_count=0` means no cap.
    Empty on failure."""
    try:
        resp = requests.get(meetup_url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"meetup fetch error: {e}", file=sys.stderr)
        return ""
    events = _extract_events_from_html(resp.text)
    return _format_meetup_events(events, event_count)


def fetch_handbook_markdown(handbook_urls: list[str], token_budget: int = 0) -> str:
    """Fetches each URL, concatenates with italic page-title headings, truncates to budget.

    verify=False because the guild wiki cert is self-managed and currently expired.
    The wiki is trusted internal content, so we accept the tradeoff.
    `token_budget <= 0` means no truncation.
    """
    sections: list[str] = []
    for url in handbook_urls:
        try:
            resp = requests.get(url, timeout=_DEFAULT_TIMEOUT, verify=False)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"handbook fetch error ({url}): {e}", file=sys.stderr)
            continue
        title = _extract_title(resp.text) or url
        body = _html_to_markdown(resp.text)
        if not body:
            continue
        sections.append(f"*{title}*\n{body}")
    markdown = "\n\n".join(sections)
    if token_budget > 0:
        char_budget = token_budget * 4
        if len(markdown) > char_budget:
            markdown = markdown[:char_budget].rstrip() + "..."
    return markdown


def _extract_events_from_html(html: str) -> list[dict]:
    """Parses upcoming events from Meetup's __NEXT_DATA__ blob.

    Meetup's group home page only embeds ~4 events as JSON-LD; the dedicated
    /events/?type=upcoming page embeds all upcoming ones in __NEXT_DATA__.
    Each event has keys like 'title', 'dateTime', 'eventUrl', 'venue'. Venue
    fields are GraphQL refs (e.g. {'__ref': 'Venue:123'}) which we resolve
    against the normalized cache at extraction time.
    """
    soup = BeautifulSoup(html, "html.parser")
    nxt = soup.find("script", id="__NEXT_DATA__")
    if not nxt or not nxt.string:
        return []
    try:
        data = json.loads(nxt.string)
    except json.JSONDecodeError:
        return []
    refs = _collect_refs(data)
    seen: set[tuple] = set()
    out: list[dict] = []
    for ev in _walk_event_shaped(data):
        key = (ev.get("title"), ev.get("dateTime"))
        if key in seen:
            continue
        seen.add(key)
        out.append(_resolve_refs(ev, refs))
    return out


def _walk_event_shaped(obj):
    """Recursively yields dicts that look like Meetup events."""
    if isinstance(obj, dict):
        if {"title", "dateTime"}.issubset(obj.keys()):
            yield obj
        for v in obj.values():
            yield from _walk_event_shaped(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_event_shaped(v)


def _collect_refs(obj) -> dict:
    """Builds a map of normalized cache entries keyed by their cache id.

    Meetup's __NEXT_DATA__ stores entries like `"Venue:27532711": {...}` at
    various depths in the tree. We collect everything that's a dict-valued
    string key, since the cache id pattern is `Type:id`.
    """
    out: dict = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and ":" in k and isinstance(v, dict) and "__typename" in v:
                out[k] = v
            out.update(_collect_refs(v))
    elif isinstance(obj, list):
        for v in obj:
            out.update(_collect_refs(v))
    return out


def _resolve_refs(ev: dict, refs: dict) -> dict:
    """Replaces shallow {'__ref': '...'} pointers in an event dict with the
    actual cache entry. One level deep is enough for our formatter's needs."""
    out: dict = {}
    for k, v in ev.items():
        if isinstance(v, dict) and "__ref" in v and v["__ref"] in refs:
            out[k] = refs[v["__ref"]]
        else:
            out[k] = v
    return out


def _format_meetup_events(events: list[dict], event_count: int) -> str:
    if not events:
        return ""
    selected = events if event_count <= 0 else events[:event_count]
    lines: list[str] = []
    for ev in selected:
        name = ev.get("title", "Untitled event")
        when = _format_event_date(ev.get("dateTime", ""))
        url = ev.get("eventUrl", "")
        venue = ev.get("venue") or {}
        venue_name = venue.get("name") if isinstance(venue, dict) else ""
        parts = [f"- **{name}**"]
        if when:
            parts.append(when)
        if venue_name:
            parts.append(venue_name)
        if url:
            parts.append(url)
        lines.append(" — ".join(parts))
    return "\n".join(lines)


def _format_event_date(iso_dt: str) -> str:
    """Converts an ISO datetime string to 'Mon Jun 09, 7:00 PM ET'.

    Falls back to the raw string when parsing fails so we never silently drop info.
    """
    if not iso_dt:
        return ""
    raw = iso_dt.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return iso_dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_ET)
    dt = dt.astimezone(_ET)
    return dt.strftime("%a %b %d, %-I:%M %p ET")


def _extract_title(html: str) -> str:
    """Pulls the page title from <title>, stripping ' | Site Name' suffix."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.split("|", 1)[0].strip()
    return ""


def _html_to_markdown(html: str) -> str:
    """BS4-based HTML → text. Strips chrome and pilcrow anchor markers.

    Also extracts text from <template> elements (wiki.js renders page content
    into server-side <template slot="contents"> blocks that body.get_text skips
    by default).
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()
    body = soup.body or soup
    parts = [body.get_text(separator="\n")]
    for template in soup.find_all("template"):
        parts.append(template.get_text(separator="\n"))
    text = "\n".join(parts).replace("¶", "")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())
