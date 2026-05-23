import requests

from cfmb.web_context import (
    _format_meetup_events,
    _html_to_markdown,
    fetch_handbook_markdown,
    fetch_meetup_markdown,
)


MEETUP_HTML = """
<html><head>
<script type="application/ld+json">
[
  {"@type": "Event", "name": "Open Make Night", "startDate": "2026-06-01T18:00:00-04:00",
   "url": "https://meetup.com/event/1", "location": {"name": "CFMG"}},
  {"@type": "Event", "name": "Laser Class", "startDate": "2026-06-08T18:00:00-04:00",
   "url": "https://meetup.com/event/2", "location": {"name": "CFMG"}}
]
</script>
</head><body><p>Events</p></body></html>
"""

HANDBOOK_HTML = """
<html>
<head><title>Handbook</title>
<script>console.log('chrome');</script>
<style>.foo { color: red }</style>
</head>
<body>
<nav>Sidebar</nav>
<header>Top</header>
<main>
<h1>Cape Fear Makers Handbook</h1>
<p>Welcome to the handbook.</p>
<h2>Safety</h2>
<p>Always wear PPE in the shop.</p>
</main>
<footer>© 2026</footer>
<aside>Aside content</aside>
</body>
</html>
"""


def test_format_meetup_events_renders_markdown():
    events = [
        {"@type": "Event", "name": "Open Make Night", "startDate": "2026-06-01T18:00:00-04:00",
         "url": "https://meetup.com/e/1", "location": {"name": "CFMG"}},
    ]
    out = _format_meetup_events(events, 5)
    assert "Open Make Night" in out
    assert "2026-06-01T18:00:00-04:00" in out
    assert "CFMG" in out
    assert "https://meetup.com/e/1" in out
    assert out.startswith("## Upcoming events")


def test_format_meetup_events_truncates_to_count():
    events = [{"@type": "Event", "name": f"Event {i}"} for i in range(10)]
    out = _format_meetup_events(events, 3)
    assert "Event 0" in out
    assert "Event 2" in out
    assert "Event 3" not in out


def test_format_meetup_events_empty_returns_empty():
    assert _format_meetup_events([], 5) == ""


def test_format_meetup_events_handles_list_location():
    events = [{"@type": "Event", "name": "Multi-loc",
               "location": [{"name": "First Place"}, {"name": "Second Place"}]}]
    out = _format_meetup_events(events, 5)
    assert "First Place" in out
    assert "Second Place" not in out


def test_html_to_markdown_strips_chrome():
    out = _html_to_markdown(HANDBOOK_HTML)
    assert "console.log" not in out
    assert "color: red" not in out
    assert "Sidebar" not in out
    assert "© 2026" not in out
    assert "Aside content" not in out
    assert "Cape Fear Makers Handbook" in out
    assert "wear PPE" in out


def test_html_to_markdown_strips_empty_lines():
    html = "<html><body><p>one</p>\n\n\n<p>two</p></body></html>"
    out = _html_to_markdown(html)
    assert out == "one\ntwo"


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


def test_fetch_handbook_returns_empty_on_request_failure(mocker):
    mocker.patch("cfmb.web_context.requests.get",
                 side_effect=requests.RequestException("boom"))
    assert fetch_handbook_markdown("http://x", 1000) == ""


def test_fetch_handbook_passes_clean_content(mocker):
    response = mocker.Mock(text=HANDBOOK_HTML)
    response.raise_for_status = mocker.Mock()
    mocker.patch("cfmb.web_context.requests.get", return_value=response)
    out = fetch_handbook_markdown("http://x", token_budget=1000)
    assert "wear PPE" in out
    assert "console.log" not in out


def test_fetch_handbook_truncates_to_budget(mocker):
    long_html = "<html><body>" + ("paragraph of text. " * 1000) + "</body></html>"
    response = mocker.Mock(text=long_html)
    response.raise_for_status = mocker.Mock()
    mocker.patch("cfmb.web_context.requests.get", return_value=response)
    out = fetch_handbook_markdown("http://x", token_budget=10)
    # token_budget * 4 chars plus the appended ellipsis
    assert len(out) <= 10 * 4 + 5
    assert out.endswith("...")
