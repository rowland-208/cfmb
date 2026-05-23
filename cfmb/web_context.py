import json
import sys

import requests
from bs4 import BeautifulSoup


_DEFAULT_TIMEOUT = 15


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


def fetch_handbook_markdown(handbook_url: str, token_budget: int) -> str:
    """Returns markdown of the handbook page truncated to token_budget. Empty on failure."""
    try:
        resp = requests.get(handbook_url, timeout=_DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"handbook fetch error: {e}", file=sys.stderr)
        return ""
    markdown = _html_to_markdown(resp.text)
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
    lines = ["## Upcoming events"]
    for ev in events[:event_count]:
        name = ev.get("name", "Untitled event")
        start = ev.get("startDate", "")
        url = ev.get("url", "")
        loc = ev.get("location") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        loc_name = loc.get("name") if isinstance(loc, dict) else ""
        parts = [f"- **{name}**"]
        if start:
            parts.append(start)
        if loc_name:
            parts.append(loc_name)
        if url:
            parts.append(url)
        lines.append(" — ".join(parts))
    return "\n".join(lines)


def _html_to_markdown(html: str) -> str:
    """BS4-based HTML → text. Strips script/style/nav/header/footer/aside chrome."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()
    body = soup.body or soup
    text = body.get_text(separator="\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())
