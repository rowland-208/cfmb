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


def fetch_meetup_markdown(meetup_url: str, event_count: int) -> str:
    """Returns markdown for up to event_count upcoming events. Empty on failure."""
    try:
        resp = requests.get(meetup_url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"meetup fetch error: {e}", file=sys.stderr)
        return ""
    events = _extract_events_from_html(resp.text)
    return _format_meetup_events(events, event_count)


def fetch_handbook_markdown(handbook_urls: list[str], token_budget: int) -> str:
    """Fetches each URL, concatenates with H3 page-title headings, truncates to budget.

    verify=False because the guild wiki cert is self-managed and currently expired.
    The wiki is trusted internal content, so we accept the tradeoff.
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
        sections.append(f"### {title}\n{body}")
    markdown = "\n\n".join(sections)
    char_budget = token_budget * 4
    if len(markdown) > char_budget:
        markdown = markdown[:char_budget].rstrip() + "..."
    return markdown


def _extract_events_from_html(html: str) -> list[dict]:
    """Parses JSON-LD Event entries from a Meetup-style page."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _iter_ld_items(data):
            if isinstance(item, dict) and item.get("@type") == "Event":
                events.append(item)
    return events


def _iter_ld_items(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_ld_items(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _iter_ld_items(data["@graph"])
        else:
            yield data


def _format_meetup_events(events: list[dict], event_count: int) -> str:
    if not events:
        return ""
    lines: list[str] = []
    for ev in events[:event_count]:
        name = ev.get("name", "Untitled event")
        when = _format_event_date(ev.get("startDate", ""))
        url = ev.get("url", "")
        loc = ev.get("location") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        loc_name = loc.get("name") if isinstance(loc, dict) else ""
        parts = [f"- **{name}**"]
        if when:
            parts.append(when)
        if loc_name:
            parts.append(loc_name)
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
