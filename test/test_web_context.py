import requests

from cfmb.web_context import (
    _extract_title,
    _format_event_date,
    _format_meetup_events,
    _html_to_markdown,
    fetch_handbook_markdown,
    fetch_meetup_markdown,
)


MEETUP_HTML = """
<html><head>
<script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {
  "events": [
    {"title": "Open Make Night", "dateTime": "2026-06-01T18:00:00-04:00",
     "eventUrl": "https://meetup.com/event/1", "venue": {"__ref": "Venue:1"}},
    {"title": "Laser Class", "dateTime": "2026-06-08T18:00:00-04:00",
     "eventUrl": "https://meetup.com/event/2", "venue": {"__ref": "Venue:1"}}
  ],
  "cache": {"Venue:1": {"__typename": "Venue", "id": "1", "name": "CFMG"}}
}}}
</script>
</head><body><p>Events</p></body></html>
"""

HANDBOOK_HTML = """
<html>
<head><title>Handbook Page | Cape Fear Makers Guild Handbook</title>
<script>console.log('chrome');</script>
<style>.foo { color: red }</style>
</head>
<body>
<nav>Sidebar</nav>
<header>Top</header>
<main>
<h1>Cape Fear Makers Handbook¶</h1>
<p>Welcome to the handbook.</p>
<h2>Safety¶</h2>
<p>Always wear PPE in the shop.</p>
</main>
<footer>© 2026</footer>
<aside>Aside content</aside>
</body>
</html>
"""

WIKI_TEMPLATE_HTML = """
<html><head><title>Rules | Wiki</title></head>
<body>
<div>
<template slot="contents">
<p>Rule 1: be kind.¶</p>
<p>Rule 2: clean up.</p>
</template>
</div>
</body></html>
"""


def test_format_event_date_utc_to_et():
    # 22:00 UTC on 2026-06-01 == 18:00 EDT (UTC-4).
    assert _format_event_date("2026-06-01T22:00:00.000Z") == "Mon Jun 01, 6:00 PM ET"


def test_format_event_date_with_offset():
    assert _format_event_date("2026-06-01T18:00:00-04:00") == "Mon Jun 01, 6:00 PM ET"


def test_format_event_date_falls_back_on_garbage():
    assert _format_event_date("not-a-date") == "not-a-date"


def test_format_event_date_empty_returns_empty():
    assert _format_event_date("") == ""


def test_format_meetup_events_uses_et_dates():
    events = [
        {"title": "Open Make Night",
         "dateTime": "2026-06-01T18:00:00-04:00",
         "eventUrl": "https://meetup.com/e/1",
         "venue": {"name": "CFMG"}},
    ]
    out = _format_meetup_events(events, 5)
    assert "Open Make Night" in out
    assert "Mon Jun 01, 6:00 PM ET" in out
    assert "2026-06-01T18:00:00-04:00" not in out
    assert "CFMG" in out
    assert "https://meetup.com/e/1" in out


def test_format_meetup_events_truncates_to_count():
    events = [{"title": f"Event {i}"} for i in range(10)]
    out = _format_meetup_events(events, 3)
    assert "Event 0" in out
    assert "Event 2" in out
    assert "Event 3" not in out


def test_format_meetup_events_zero_count_returns_all():
    events = [{"title": f"Event {i}"} for i in range(10)]
    out = _format_meetup_events(events, 0)
    assert "Event 0" in out
    assert "Event 9" in out


def test_format_meetup_events_empty_returns_empty():
    assert _format_meetup_events([], 5) == ""


def test_format_meetup_events_handles_missing_venue():
    events = [{"title": "No venue", "dateTime": "2026-06-01T18:00:00-04:00"}]
    out = _format_meetup_events(events, 5)
    assert "No venue" in out
    assert "Mon Jun 01" in out


def test_html_to_markdown_strips_chrome():
    out = _html_to_markdown(HANDBOOK_HTML)
    assert "console.log" not in out
    assert "color: red" not in out
    assert "Sidebar" not in out
    assert "© 2026" not in out
    assert "Aside content" not in out
    assert "Cape Fear Makers Handbook" in out
    assert "wear PPE" in out


def test_html_to_markdown_strips_pilcrows():
    out = _html_to_markdown(HANDBOOK_HTML)
    assert "¶" not in out


def test_html_to_markdown_extracts_template_content():
    out = _html_to_markdown(WIKI_TEMPLATE_HTML)
    assert "Rule 1: be kind." in out
    assert "Rule 2: clean up." in out


def test_html_to_markdown_strips_empty_lines():
    html = "<html><body><p>one</p>\n\n\n<p>two</p></body></html>"
    out = _html_to_markdown(html)
    assert out == "one\ntwo"


def test_extract_title_strips_suffix():
    assert _extract_title(HANDBOOK_HTML) == "Handbook Page"


def test_extract_title_empty_when_missing():
    assert _extract_title("<html><body>no title</body></html>") == ""


def test_fetch_meetup_returns_empty_on_request_failure(mocker):
    mocker.patch("cfmb.web_context.requests.get",
                 side_effect=requests.RequestException("boom"))
    assert fetch_meetup_markdown("http://x", 5) == ""


def test_fetch_meetup_parses_real_html(mocker):
    response = mocker.Mock(text=MEETUP_HTML)
    response.raise_for_status = mocker.Mock()
    mocker.patch("cfmb.web_context.requests.get", return_value=response)
    out = fetch_meetup_markdown("http://x", 5)
    assert "Open Make Night" in out
    assert "Laser Class" in out
    # Venue ref was resolved to the normalized cache entry.
    assert "CFMG" in out


def test_fetch_handbook_empty_list_returns_empty():
    assert fetch_handbook_markdown([], 1000) == ""


def test_fetch_handbook_skips_failed_urls(mocker):
    ok_response = mocker.Mock(text=HANDBOOK_HTML)
    ok_response.raise_for_status = mocker.Mock()

    def get(url, timeout=None, verify=None):
        if "good" in url:
            return ok_response
        raise requests.RequestException("nope")

    mocker.patch("cfmb.web_context.requests.get", side_effect=get)
    out = fetch_handbook_markdown(["http://bad/", "http://good/"], 1000)
    assert "wear PPE" in out
    assert "Handbook Page" in out  # title heading


def test_fetch_handbook_concatenates_multiple_pages(mocker):
    response_a = mocker.Mock(text="<html><head><title>A | Site</title></head>"
                                  "<body><p>alpha content</p></body></html>")
    response_a.raise_for_status = mocker.Mock()
    response_b = mocker.Mock(text="<html><head><title>B | Site</title></head>"
                                  "<body><p>beta content</p></body></html>")
    response_b.raise_for_status = mocker.Mock()
    mocker.patch("cfmb.web_context.requests.get",
                 side_effect=[response_a, response_b])
    out = fetch_handbook_markdown(["http://a/", "http://b/"], 1000)
    assert out.startswith("*A*\n")
    assert "alpha content" in out
    assert "*B*\n" in out
    assert "beta content" in out


def test_fetch_handbook_truncates_to_budget(mocker):
    long_html = ("<html><head><title>Big | Site</title></head><body>"
                 + ("paragraph of text. " * 1000) + "</body></html>")
    response = mocker.Mock(text=long_html)
    response.raise_for_status = mocker.Mock()
    mocker.patch("cfmb.web_context.requests.get", return_value=response)
    out = fetch_handbook_markdown(["http://x/"], token_budget=10)
    assert len(out) <= 10 * 4 + 5
    assert out.endswith("...")


def test_fetch_handbook_zero_budget_no_truncation(mocker):
    long_body = "paragraph of text. " * 1000
    long_html = f"<html><head><title>Big | Site</title></head><body>{long_body}</body></html>"
    response = mocker.Mock(text=long_html)
    response.raise_for_status = mocker.Mock()
    mocker.patch("cfmb.web_context.requests.get", return_value=response)
    out = fetch_handbook_markdown(["http://x/"], token_budget=0)
    assert not out.endswith("...")
    assert len(out) > 10 * 4 + 5
