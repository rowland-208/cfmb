from cfmb.prompt import (
    _date_from_timestamp,
    build_chain_messages,
    build_system_prompt,
    render_discord_content,
)


def test_render_discord_content_empty_returns_empty():
    assert render_discord_content([]) == ""


def test_render_discord_content_groups_by_channel_and_day():
    rows = [
        {"channel_name": "general", "timestamp": "2026-05-22 09:00:00",
         "username": "alice", "content": "morning"},
        {"channel_name": "general", "timestamp": "2026-05-22 09:05:00",
         "username": "bob", "content": "hey"},
        {"channel_name": "general", "timestamp": "2026-05-23 10:00:00",
         "username": "alice", "content": "new day"},
        {"channel_name": "ai-stuff", "timestamp": "2026-05-23 11:00:00",
         "username": "carol", "content": "llama 4?"},
    ]
    out = render_discord_content(rows)
    expected = (
        "### general\n"
        "**2026-05-22**\n"
        "- alice: morning\n"
        "- bob: hey\n"
        "**2026-05-23**\n"
        "- alice: new day\n"
        "### ai-stuff\n"
        "**2026-05-23**\n"
        "- carol: llama 4?"
    )
    assert out == expected


def test_render_discord_content_collapses_whitespace():
    rows = [{"channel_name": "general", "timestamp": "2026-05-23 09:00:00",
             "username": "alice", "content": "line one\n\n  line two\tline three"}]
    out = render_discord_content(rows)
    assert out == "### general\n**2026-05-23**\n- alice: line one line two line three"


def test_render_discord_content_handles_missing_channel():
    rows = [{"channel_name": None, "timestamp": "2026-05-23 09:00:00",
             "username": "alice", "content": "dm-ish"}]
    out = render_discord_content(rows)
    assert "### unknown" in out


def test_render_discord_content_handles_missing_username():
    rows = [{"channel_name": "general", "timestamp": "2026-05-23 09:00:00",
             "username": None, "content": "hi"}]
    out = render_discord_content(rows)
    assert "- unknown: hi" in out


def test_build_system_prompt_concatenates_sections():
    out = build_system_prompt(
        base="Base prompt.",
        meetup="- **Event 1**",
        handbook="Handbook text.",
        discord="### general\n**2026-05-23**\n- alice: hi",
    )
    expected = (
        "Base prompt.\n\n"
        "## Upcoming events\n- **Event 1**\n\n"
        "## Handbook\nHandbook text.\n\n"
        "## Recent guild activity\n### general\n**2026-05-23**\n- alice: hi"
    )
    assert out == expected


def test_build_system_prompt_omits_empty_sections():
    out = build_system_prompt(base="Base.", meetup="", handbook="", discord="")
    assert out == "Base."


def test_build_system_prompt_omits_only_meetup_when_empty():
    out = build_system_prompt(base="Base.", meetup="",
                              handbook="Handbook.", discord="discord")
    assert "## Upcoming events" not in out
    assert "## Handbook" in out
    assert "## Recent guild activity" in out


def test_build_chain_messages_derives_role():
    rows = [
        {"user_id": "user1", "content": "hi"},
        {"user_id": "BOT", "content": "hello back"},
        {"user_id": "user2", "content": "yo"},
    ]
    out = build_chain_messages(rows, bot_user_id="BOT")
    assert out == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello back"},
        {"role": "user", "content": "yo"},
    ]


def test_build_chain_messages_handles_int_str_mismatch():
    rows = [{"user_id": "12345", "content": "hi"}]
    out = build_chain_messages(rows, bot_user_id=12345)
    assert out == [{"role": "assistant", "content": "hi"}]


def test_build_chain_messages_empty():
    assert build_chain_messages([], "BOT") == []


def test_date_from_timestamp_sqlite_format():
    assert _date_from_timestamp("2026-05-23 16:10:01") == "2026-05-23"


def test_date_from_timestamp_iso_format():
    assert _date_from_timestamp("2026-05-23T16:10:01") == "2026-05-23"


def test_date_from_timestamp_empty():
    assert _date_from_timestamp("") == "unknown-date"
