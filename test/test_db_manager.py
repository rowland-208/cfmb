import os
import sqlite3
import tempfile

import pytest

from cfmb.db_manager import DatabaseManager


BOT_ID = "999999999"


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as f:
        path = f.name
    manager = DatabaseManager(path)
    manager.initialize_db()
    yield manager
    os.remove(path)


def _write(db, *, message_id, content="hi", user_id="u1", username="alice",
           channel_id="c1", channel_name="general", reply_to=None,
           is_mention=False, chain_id_override=None, server_id="s1"):
    return db.write_message(
        server_id=server_id, message_id=message_id, user_id=user_id,
        username=username, channel_id=channel_id, channel_name=channel_name,
        content=content, reply_to_message_id=reply_to, is_mention=is_mention,
        bot_user_id=BOT_ID, chain_id_override=chain_id_override,
    )


def test_initialize_db_creates_messages_table(db):
    with db._get_connection() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    expected = {"id", "server_id", "message_id", "chain_id", "user_id",
                "username", "channel_id", "channel_name", "content", "timestamp"}
    assert expected <= cols


def test_initialize_db_creates_indexes(db):
    with db._get_connection() as conn:
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='messages'"
        ).fetchall()}
    assert "idx_messages_chain" in names
    assert "idx_messages_server_time" in names


def test_write_message_no_mention_no_reply_stays_null(db):
    chain_id = _write(db, message_id="m1", content="just chatting")
    assert chain_id is None
    with db._get_connection() as conn:
        row = conn.execute("SELECT chain_id FROM messages WHERE message_id='m1'").fetchone()
    assert row[0] is None


def test_write_message_mention_starts_new_chain(db):
    chain_id = _write(db, message_id="m1", content="@bot hello", is_mention=True)
    assert chain_id == "m1"


def test_write_message_reply_to_chain_inherits(db):
    _write(db, message_id="parent", is_mention=True)  # chain_id = "parent"
    chain_id = _write(db, message_id="m2", content="follow-up", reply_to="parent")
    assert chain_id == "parent"


def test_write_message_reply_to_chainless_stays_null(db):
    _write(db, message_id="parent", content="random")  # chain_id = NULL
    chain_id = _write(db, message_id="m2", content="reply", reply_to="parent")
    assert chain_id is None


def test_write_message_reply_to_unknown_falls_through(db):
    chain_id = _write(db, message_id="m1", reply_to="nonexistent")
    assert chain_id is None
    chain_id = _write(db, message_id="m2", reply_to="nonexistent", is_mention=True)
    assert chain_id == "m2"


def test_write_message_chain_override_wins(db):
    chain_id = _write(db, message_id="m1", chain_id_override="forced-chain")
    assert chain_id == "forced-chain"
    with db._get_connection() as conn:
        row = conn.execute("SELECT chain_id FROM messages WHERE message_id='m1'").fetchone()
    assert row[0] == "forced-chain"


def test_write_message_bot_reply_uses_override(db):
    _write(db, message_id="user-msg", is_mention=True)
    chain_id = _write(db, message_id="bot-msg", user_id=BOT_ID, username="bot",
                      reply_to="user-msg", chain_id_override="user-msg")
    assert chain_id == "user-msg"


def test_write_message_duplicate_message_id_silently_ignored(db):
    _write(db, message_id="m1", content="first", is_mention=True)
    # Should not raise on duplicate insert; should preserve first row.
    _write(db, message_id="m1", content="second")
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT content, chain_id FROM messages WHERE message_id='m1'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "first"
    assert rows[0][1] == "m1"


def test_get_chain_messages_ordered_oldest_first(db):
    _write(db, message_id="m1", content="first", is_mention=True)
    _write(db, message_id="m2", content="second", reply_to="m1")
    _write(db, message_id="m3", content="third", reply_to="m1")
    rows = db.get_chain_messages("m1")
    contents = [r["content"] for r in rows]
    assert contents == ["first", "second", "third"]
    assert rows[0]["user_id"] == "u1"
    assert rows[0]["username"] == "alice"


def test_get_chain_messages_empty(db):
    assert db.get_chain_messages("nonexistent") == []


def test_get_recent_discord_messages_excludes_current_chain(db):
    _write(db, message_id="chain-parent", is_mention=True)
    _write(db, message_id="chain-child", reply_to="chain-parent", content="in-chain")
    _write(db, message_id="other", content="elsewhere")
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id="chain-parent",
        excluded_channel_ids=[],
    )
    contents = [r["content"] for r in rows]
    assert "in-chain" not in contents
    assert "elsewhere" in contents


def test_get_recent_discord_messages_includes_other_chains(db):
    _write(db, message_id="current", is_mention=True)
    _write(db, message_id="other-chain", content="callback fodder", is_mention=True,
           channel_id="c2", channel_name="other")
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id="current", excluded_channel_ids=[],
    )
    assert "callback fodder" in [r["content"] for r in rows]


def test_get_recent_discord_messages_filters_excluded_channels(db):
    _write(db, message_id="m1", content="keep me", channel_id="good", channel_name="good")
    _write(db, message_id="m2", content="drop me", channel_id="bad", channel_name="bad")
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id=None, excluded_channel_ids=["bad"],
    )
    contents = [r["content"] for r in rows]
    assert "keep me" in contents
    assert "drop me" not in contents


def test_get_recent_discord_messages_filters_by_server(db):
    _write(db, message_id="m1", content="ours", server_id="s1")
    _write(db, message_id="m2", content="theirs", server_id="s2")
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id=None, excluded_channel_ids=[],
    )
    contents = [r["content"] for r in rows]
    assert "ours" in contents
    assert "theirs" not in contents


def test_get_recent_discord_messages_filters_by_time(db):
    _write(db, message_id="recent", content="recent")
    # Backdate a row older than the 7-day window.
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (server_id, message_id, chain_id, user_id, username, "
            "channel_id, channel_name, content, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("s1", "old", None, "u1", "alice", "c1", "general", "ancient",
             "2020-01-01 00:00:00"),
        )
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id=None, excluded_channel_ids=[], days=7,
    )
    contents = [r["content"] for r in rows]
    assert "recent" in contents
    assert "ancient" not in contents


def test_get_recent_discord_messages_handles_null_current_chain(db):
    _write(db, message_id="m1", content="general chatter")
    _write(db, message_id="m2", content="bot conversation", is_mention=True)
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id=None, excluded_channel_ids=[],
    )
    contents = [r["content"] for r in rows]
    assert "general chatter" in contents
    assert "bot conversation" in contents


def test_get_recent_discord_messages_newest_first(db):
    with db._get_connection() as conn:
        for i, ts in enumerate([
            "2099-01-01 09:00:00", "2099-01-01 10:00:00", "2099-01-01 11:00:00",
        ]):
            conn.execute(
                "INSERT INTO messages (server_id, message_id, chain_id, user_id, username, "
                "channel_id, channel_name, content, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("s1", f"m{i}", None, "u1", "alice", "c1", "general", f"msg-{i}", ts),
            )
    rows = db.get_recent_discord_messages(
        server_id="s1", current_chain_id=None, excluded_channel_ids=[], days=100000,
    )
    assert [r["content"] for r in rows] == ["msg-2", "msg-1", "msg-0"]
