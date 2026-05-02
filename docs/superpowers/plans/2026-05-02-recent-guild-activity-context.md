# Recent guild activity in @mention context — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the bot is @mentioned, append a markdown-formatted "Recent guild activity (past 3 days)" block to its system prompt — sourced from `raw_messages`, capped at the 300 globally most-recent non-bot messages, excluding channels listed in `DEV_EXCLUDED_CHANNELS`.

**Architecture:** One new query helper `get_recent_user_messages` in `cfmb/db_manager.py`. One pure formatter `_format_activity_block` in `cfmb/bot.py`. One call site in `_build_system_prompt`. The standalone `export_messages.py` is refactored to call the same helper (passing `days=7`, `limit=None`, and the IDs of `cfmb`/`cfmb-dev`).

**Tech Stack:** Python 3.12, SQLite via stdlib `sqlite3`, pytest with pytest-asyncio + pytest-mock. Bot service managed via `systemctl --user`.

**Spec:** `docs/superpowers/specs/2026-05-02-recent-guild-activity-context-design.md`

---

## File map

- **Modify:** `cfmb/db_manager.py` — add `get_recent_user_messages` next to other `raw_messages` helpers (around line 305, after `get_raw_messages_date_range`).
- **Modify:** `cfmb/bot.py` — add `_format_activity_block` near `_build_system_prompt` (around line 803), then call helper + formatter inside `_build_system_prompt`.
- **Modify:** `test/test_db_manager.py` — new tests for `get_recent_user_messages`.
- **Modify:** `test/test_bot.py` — new tests for `_format_activity_block`.
- **Modify:** `export_messages.py` — replace inline SQL with a call to the helper.

---

## Task 1: Add `get_recent_user_messages` helper to db_manager

**Files:**
- Modify: `cfmb/db_manager.py` (insert new method after `get_raw_messages_date_range`, around line 329)
- Test: `test/test_db_manager.py` (append new tests at end of file)

- [ ] **Step 1: Write the failing tests**

Append to `test/test_db_manager.py`:

```python
def _seed_raw_message(db_manager, *, server_id="s1", message_id="m", user_id="u1",
                      username="alice", content="hi", channel_id="c1",
                      channel_name="general", timestamp=None):
    """Insert a raw_messages row with an optional explicit timestamp.

    write_raw_message hardcodes CURRENT_TIMESTAMP, so historical-row tests
    must go through raw SQL.
    """
    with db_manager._get_connection() as conn:
        cur = conn.cursor()
        if timestamp is None:
            cur.execute(
                "INSERT INTO raw_messages (server_id, message_id, user_id, username, content, channel_id, channel_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (server_id, message_id, user_id, username, content, channel_id, channel_name),
            )
        else:
            cur.execute(
                "INSERT INTO raw_messages (server_id, message_id, user_id, username, content, channel_id, channel_name, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (server_id, message_id, user_id, username, content, channel_id, channel_name, timestamp),
            )


def test_get_recent_user_messages_filters_bot_and_window(db_manager):
    """Excludes bot user, messages outside window, slash-commands, and NULL channel_name."""
    bot_id = "BOT"
    # Inside window, real user — KEEP
    _seed_raw_message(db_manager, message_id="1", user_id="u1", username="alice",
                      content="hello", channel_name="general", channel_id="c-gen")
    # Inside window, bot user — DROP
    _seed_raw_message(db_manager, message_id="2", user_id=bot_id, username="bot",
                      content="reply", channel_name="general", channel_id="c-gen")
    # Inside window, slash command — DROP
    _seed_raw_message(db_manager, message_id="3", user_id="u1", username="alice",
                      content="/help", channel_name="general", channel_id="c-gen")
    # Inside window, NULL channel_name — DROP
    _seed_raw_message(db_manager, message_id="4", user_id="u1", username="alice",
                      content="dm-ish", channel_name=None, channel_id="c-gen")
    # Outside window (10 days ago) — DROP
    _seed_raw_message(db_manager, message_id="5", user_id="u1", username="alice",
                      content="ancient", channel_name="general", channel_id="c-gen",
                      timestamp="2020-01-01 00:00:00")

    rows = db_manager.get_recent_user_messages(
        server_id="s1", days=3, limit=300, excluded_channel_ids=[], bot_user_id=bot_id
    )
    assert len(rows) == 1
    assert rows[0]["content"] == "hello"
    assert rows[0]["username"] == "alice"
    assert rows[0]["channel_name"] == "general"
    assert "day" in rows[0]


def test_get_recent_user_messages_excludes_channels_and_orders(db_manager):
    """Excluded channel_ids are dropped; output is ordered by channel_name, day, timestamp."""
    _seed_raw_message(db_manager, message_id="a", user_id="u1", username="alice",
                      content="msg-a", channel_name="general", channel_id="c-gen",
                      timestamp="2099-01-02 09:00:00")
    _seed_raw_message(db_manager, message_id="b", user_id="u1", username="alice",
                      content="msg-b", channel_name="general", channel_id="c-gen",
                      timestamp="2099-01-02 08:00:00")
    _seed_raw_message(db_manager, message_id="c", user_id="u1", username="alice",
                      content="msg-c", channel_name="ai-stuff", channel_id="c-ai",
                      timestamp="2099-01-02 10:00:00")
    _seed_raw_message(db_manager, message_id="d", user_id="u1", username="alice",
                      content="msg-d", channel_name="cfmb-dev", channel_id="c-dev",
                      timestamp="2099-01-02 09:30:00")

    # The seed timestamps are in the future, so a generous window keeps them.
    rows = db_manager.get_recent_user_messages(
        server_id="s1", days=100000, limit=300,
        excluded_channel_ids=["c-dev"], bot_user_id="BOT",
    )
    contents = [r["content"] for r in rows]
    # ai-stuff comes before general alphabetically; within general, 08:00 before 09:00.
    assert contents == ["msg-c", "msg-b", "msg-a"]


def test_get_recent_user_messages_global_recency_cap(db_manager):
    """`limit` keeps the N most-recent messages globally, then re-orders by channel/day/time."""
    for i in range(5):
        _seed_raw_message(
            db_manager, message_id=f"x{i}", user_id="u1", username="alice",
            content=f"m{i}", channel_name="general", channel_id="c-gen",
            timestamp=f"2099-01-0{i+1} 12:00:00",
        )

    rows = db_manager.get_recent_user_messages(
        server_id="s1", days=100000, limit=2,
        excluded_channel_ids=[], bot_user_id="BOT",
    )
    # Most-recent 2 are m3, m4 — re-ordered ascending by timestamp.
    assert [r["content"] for r in rows] == ["m3", "m4"]


def test_get_recent_user_messages_limit_none_returns_all(db_manager):
    """limit=None disables the LIMIT clause."""
    for i in range(4):
        _seed_raw_message(
            db_manager, message_id=f"y{i}", user_id="u1", username="alice",
            content=f"m{i}", channel_name="general", channel_id="c-gen",
            timestamp=f"2099-01-0{i+1} 12:00:00",
        )

    rows = db_manager.get_recent_user_messages(
        server_id="s1", days=100000, limit=None,
        excluded_channel_ids=[], bot_user_id="BOT",
    )
    assert len(rows) == 4


def test_get_recent_user_messages_empty(db_manager):
    """Empty raw_messages returns []."""
    rows = db_manager.get_recent_user_messages(
        server_id="s1", days=3, limit=300, excluded_channel_ids=[], bot_user_id="BOT",
    )
    assert rows == []
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run: `./test.sh -k get_recent_user_messages`
Expected: 5 failures with `AttributeError: 'DatabaseManager' object has no attribute 'get_recent_user_messages'`.

- [ ] **Step 3: Implement the helper**

In `cfmb/db_manager.py`, insert this method immediately after `get_raw_messages_date_range` (around line 329):

```python
    def get_recent_user_messages(self, server_id, days, limit, excluded_channel_ids, bot_user_id):
        """Returns recent non-bot user messages for context injection.

        Globally caps to the `limit` most-recent rows within `days` days, then
        re-orders the kept rows by channel_name, day, timestamp for grouped
        rendering. `limit=None` disables the cap. `excluded_channel_ids` is an
        iterable of channel_id strings to skip.
        """
        excluded = list(excluded_channel_ids)
        not_in_clause = ""
        params = [server_id, bot_user_id, f"-{int(days)} days"]
        if excluded:
            placeholders = ",".join("?" * len(excluded))
            not_in_clause = f"AND channel_id NOT IN ({placeholders})"
            params.extend(excluded)
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(int(limit))

        sql = f"""
            SELECT channel_name, DATE(timestamp) AS day, username, content
            FROM (
                SELECT channel_name, timestamp, username, content
                FROM raw_messages
                WHERE server_id = ?
                  AND user_id != ?
                  AND timestamp >= DATETIME('now', ?)
                  AND channel_name IS NOT NULL
                  AND content NOT LIKE '/%'
                  {not_in_clause}
                ORDER BY timestamp DESC
                {limit_clause}
            )
            ORDER BY channel_name, day, timestamp
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            return [
                {"channel_name": channel_name, "day": day, "username": username, "content": content}
                for channel_name, day, username, content in rows
            ]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `./test.sh -k get_recent_user_messages`
Expected: 5 passed.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `./test.sh`
Expected: all green (existing pass count + 5 new).

- [ ] **Step 6: Commit**

```bash
git add cfmb/db_manager.py test/test_db_manager.py
git commit -m "$(cat <<'EOF'
Add get_recent_user_messages helper to DatabaseManager

Returns non-bot raw_messages within a day window, capped to the
globally most-recent N rows, with channel-id exclusions and the
standard hygiene filters (channel_name not null, slash commands
skipped). Used by both the @mention context injection and the
standalone export script.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `_format_activity_block` formatter to bot.py

**Files:**
- Modify: `cfmb/bot.py` (insert new function above `_build_system_prompt`, around line 800)
- Test: `test/test_bot.py` (append new tests)

- [ ] **Step 1: Write the failing tests**

Append to `test/test_bot.py`:

```python
from cfmb.bot import _format_activity_block


def test_format_activity_block_groups_by_channel_and_day():
    rows = [
        {"channel_name": "ai-stuff", "day": "2026-04-30", "username": "alice", "content": "ml stuff"},
        {"channel_name": "general", "day": "2026-04-30", "username": "bob", "content": "morning"},
        {"channel_name": "general", "day": "2026-05-01", "username": "carol", "content": "anyone here"},
        {"channel_name": "general", "day": "2026-05-01", "username": "bob", "content": "yep"},
    ]
    out = _format_activity_block(rows)
    expected = (
        "# ai-stuff\n"
        "## 2026-04-30\n"
        "- alice: ml stuff\n"
        "# general\n"
        "## 2026-04-30\n"
        "- bob: morning\n"
        "## 2026-05-01\n"
        "- carol: anyone here\n"
        "- bob: yep"
    )
    assert out == expected


def test_format_activity_block_collapses_whitespace_in_content():
    rows = [
        {"channel_name": "general", "day": "2026-05-01", "username": "alice",
         "content": "line one\n\n  line two\tline three"},
    ]
    out = _format_activity_block(rows)
    assert out == "# general\n## 2026-05-01\n- alice: line one line two line three"


def test_format_activity_block_empty_returns_empty_string():
    assert _format_activity_block([]) == ""
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run: `./test.sh -k _format_activity_block or format_activity_block`
Expected: ImportError or `AttributeError: module 'cfmb.bot' has no attribute '_format_activity_block'`.

- [ ] **Step 3: Implement the formatter**

In `cfmb/bot.py`, immediately above `async def _build_system_prompt(...)` (currently at line 803), add:

```python
def _format_activity_block(rows):
    """Renders rows from get_recent_user_messages as channel/day-grouped markdown bullets."""
    if not rows:
        return ""
    lines = []
    current_channel = current_day = None
    for row in rows:
        if row["channel_name"] != current_channel:
            lines.append(f"# {row['channel_name']}")
            current_channel = row["channel_name"]
            current_day = None
        if row["day"] != current_day:
            lines.append(f"## {row['day']}")
            current_day = row["day"]
        single_line = " ".join(row["content"].split())
        lines.append(f"- {row['username']}: {single_line}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `./test.sh -k format_activity_block`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add cfmb/bot.py test/test_bot.py
git commit -m "$(cat <<'EOF'
Add _format_activity_block formatter for guild-activity context

Pure helper that groups rows from get_recent_user_messages into the
markdown layout used by the export script: '# channel' / '## date'
/ '- username: content', with multi-line content collapsed to a
single line. Returns '' for empty input so callers can skip the
whole section.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Wire the helper and formatter into `_build_system_prompt`

**Files:**
- Modify: `cfmb/bot.py` — extend `_build_system_prompt` (around lines 803–829)

- [ ] **Step 1: Read the current `_build_system_prompt` to confirm insertion point**

Run: `sed -n '800,830p' cfmb/bot.py` (or open the file).
Expected: see the function ending with `return system_prompt` after the `## User profile` block.

- [ ] **Step 2: Add the call after the `## User profile` block**

In `cfmb/bot.py`, change the tail of `_build_system_prompt` from:

```python
    if profile_row:
        system_prompt["content"] += f"\n\n## User profile\n{profile_row['profile']}"
    else:
        system_prompt["content"] += "\n\n## User profile\nThis user has not been active recently and no profile is available."

    return system_prompt
```

to:

```python
    if profile_row:
        system_prompt["content"] += f"\n\n## User profile\n{profile_row['profile']}"
    else:
        system_prompt["content"] += "\n\n## User profile\nThis user has not been active recently and no profile is available."

    excluded_channel_ids = (
        [c.strip() for c in config.DEV_EXCLUDED_CHANNELS.split(",") if c.strip()]
        if config.DEV_EXCLUDED_CHANNELS
        else []
    )
    activity_rows = db_manager.get_recent_user_messages(
        server_id,
        days=3,
        limit=300,
        excluded_channel_ids=excluded_channel_ids,
        bot_user_id=str(config.BOT_USER_ID),
    )
    activity_block = _format_activity_block(activity_rows)
    if activity_block:
        system_prompt["content"] += f"\n\n## Recent guild activity (past 3 days)\n{activity_block}"

    return system_prompt
```

- [ ] **Step 3: Run the full test suite**

Run: `./test.sh`
Expected: all green. (No new tests for this wiring — it is a thin call site over two helpers that both have their own tests. Adding a Discord-mocked integration test costs more than it adds.)

- [ ] **Step 4: Commit**

```bash
git add cfmb/bot.py
git commit -m "$(cat <<'EOF'
Inject recent guild activity into @mention system prompt

Append a 'Recent guild activity (past 3 days)' markdown section to
the system prompt assembled in _build_system_prompt, sourced from
the new get_recent_user_messages helper. Caps at 300 globally
most-recent non-bot messages and honors DEV_EXCLUDED_CHANNELS.
Section is omitted when there are no rows to render.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Refactor `export_messages.py` to call the helper

**Files:**
- Modify: `export_messages.py`

- [ ] **Step 1: Replace the script body with a call to the helper**

Open `export_messages.py` and replace its contents with:

```python
#!/usr/bin/env python3
"""Export the past week of user messages to markdown grouped by channel and date."""
import sqlite3
import sys
from pathlib import Path

from cfmb.db_manager import DatabaseManager

DB_PATH = Path(__file__).parent / "cfmb_db.sqlite"
EXCLUDED_CHANNEL_NAMES = ("cfmb", "cfmb-dev")


def _read_bot_user_id() -> str:
    for line in (Path.home() / ".cfmb").read_text().splitlines():
        if line.startswith("BOT_USER_ID="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("BOT_USER_ID not found in ~/.cfmb")


def _resolve_channel_ids(db_path: Path, names: tuple[str, ...]) -> list[str]:
    placeholders = ",".join("?" * len(names))
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT DISTINCT channel_id FROM raw_messages WHERE channel_name IN ({placeholders})",
            names,
        )
        return [row[0] for row in cur.fetchall() if row[0]]


def _resolve_server_id(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT server_id FROM raw_messages WHERE server_id IS NOT NULL LIMIT 1")
        row = cur.fetchone()
    if not row:
        raise RuntimeError("No raw_messages rows found; cannot infer server_id.")
    return row[0]


def main(out_path: str = "messages_past_week.md") -> None:
    bot_user_id = _read_bot_user_id()
    excluded_ids = _resolve_channel_ids(DB_PATH, EXCLUDED_CHANNEL_NAMES)
    server_id = _resolve_server_id(DB_PATH)

    db = DatabaseManager(str(DB_PATH))
    rows = db.get_recent_user_messages(
        server_id=server_id,
        days=7,
        limit=None,
        excluded_channel_ids=excluded_ids,
        bot_user_id=bot_user_id,
    )

    lines: list[str] = []
    current_channel = current_day = None
    for row in rows:
        if row["channel_name"] != current_channel:
            lines.append(f"# {row['channel_name']}")
            current_channel = row["channel_name"]
            current_day = None
        if row["day"] != current_day:
            lines.append(f"## {row['day']}")
            current_day = row["day"]
        single_line = " ".join(row["content"].split())
        lines.append(f"- {row['username']}: {single_line}")

    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} messages to {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "messages_past_week.md")
```

- [ ] **Step 2: Run the script and confirm output looks right**

Run: `/home/evilai/repos/cfmb/.venv/bin/python export_messages.py /tmp/messages_smoke.md`
Expected: prints `Wrote N messages to /tmp/messages_smoke.md` for some N > 0; the file starts with a `# <channel>` heading.

Run: `head -10 /tmp/messages_smoke.md`
Expected: looks like the previous export — channel heading, date heading, bulleted messages.

- [ ] **Step 3: Commit**

```bash
git add export_messages.py
git commit -m "$(cat <<'EOF'
Refactor export_messages.py onto get_recent_user_messages

The script now delegates the query to DatabaseManager so the bot's
@mention context and the standalone export share one code path.
Channel exclusions still go by name (resolved to IDs at startup);
window stays at 7 days with no row cap.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Manual verification and bot restart

**Files:** none modified.

- [ ] **Step 1: Run the full test suite once more**

Run: `./test.sh`
Expected: all green.

- [ ] **Step 2: Restart the bot**

Run: `systemctl --user restart cfmb`
Then: `systemctl --user status cfmb --no-pager | head -10`
Expected: `Active: active (running)`.

- [ ] **Step 3: Smoke-test in Discord**

In a non-`#cfmb-dev` channel, @mention the bot with a question that depends on recent guild activity (e.g. "@Maker bot what's been going on this week?"). Confirm the reply references actual recent messages from across channels.

If something looks off, check the bot's stdout via `journalctl --user -u cfmb -n 100 --no-pager` for query errors.

- [ ] **Step 4: No commit needed** — verification only.

---

## Self-review notes

- Spec coverage: helper (Tasks 1), formatter (Task 2), wire-up to `_build_system_prompt` (Task 3), `export_messages.py` refactor (Task 4), tests for helper + formatter (Tasks 1–2). Bot integration test deliberately skipped per spec ("thin formatter on top of tested helper").
- Helper signature in plan tests includes `bot_user_id` as a parameter — slightly different from the spec, which implied reading `config.BOT_USER_ID` inside the helper. Passing it in keeps `db_manager` free of config imports and makes the helper trivially testable; the call site in `_build_system_prompt` supplies `config.BOT_USER_ID` explicitly.
- Type consistency: helper returns `list[dict]` with keys `channel_name`, `day`, `username`, `content` everywhere — tests, formatter, and call site all agree.
- All steps include exact code or exact commands. No TBDs.
