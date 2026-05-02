# Recent guild activity in @mention context — design

## Goal

When the bot is @mentioned, include the past 3 days of non-bot guild messages in its system prompt so replies can reflect recent cross-channel activity.

## Non-goals

- No new slash command, scheduled task, or user-facing artifact. The export markdown is an internal prompt section, not a posted digest.
- No summarization step. The raw transcript is injected verbatim within a size cap.
- No changes to the daily summary, profile, or newsletter pipelines.

## Architecture

One new method in `cfmb/db_manager.py`. One new block appended inside `_build_system_prompt` in `cfmb/bot.py`. The standalone `export_messages.py` is refactored to call the same helper. No new files, no new commands, no new scheduled tasks.

## Data flow

1. User @mentions the bot in any channel.
2. The existing `_build_system_prompt(message, server_id, user_content, id_to_name)` path runs.
3. After the existing `## User profile` block, the function calls `db_manager.get_recent_user_messages(server_id, days=3, limit=300, excluded_channel_ids=...)`.
4. Returned rows are formatted as markdown:
   ```
   # {channel_name}
   ## {YYYY-MM-DD}
   - {username}: {content}
   ```
5. The block is appended under heading `## Recent guild activity (past 3 days)`.
6. If the helper returns zero rows, the section is omitted entirely.

The helper is called on every @mention. The query is a single indexed SQLite read against `raw_messages` on a local file; cost is negligible compared to LLM inference. No caching layer.

## Components

### `db_manager.get_recent_user_messages`

Signature:

```python
def get_recent_user_messages(
    self,
    server_id: str,
    days: int,
    limit: int | None,
    excluded_channel_ids: Iterable[str],
) -> list[dict]:
```

Returns rows shaped as `{"channel_name", "day", "username", "content"}`, ordered by `channel_name`, then `day`, then `timestamp`. When `limit` is an int, returns at most that many globally most-recent messages (not per-channel). When `limit` is `None`, returns all matching rows.

The query also applies the same hygiene filters used by the other `raw_messages` helpers: `channel_name IS NOT NULL` and `content NOT LIKE '/%'` (skips slash-command invocations like `/cfmb-set`).

SQL (with non-empty `excluded_channel_ids`):

```sql
SELECT channel_name, DATE(timestamp) AS day, username, content
FROM (
    SELECT channel_name, timestamp, username, content
    FROM raw_messages
    WHERE server_id = ?
      AND user_id != ?                          -- BOT_USER_ID
      AND timestamp >= DATETIME('now', ?)       -- '-{days} days'
      AND channel_name IS NOT NULL
      AND content NOT LIKE '/%'
      AND channel_id NOT IN ({placeholders})    -- excluded_channel_ids
    ORDER BY timestamp DESC
    LIMIT ?
)
ORDER BY channel_name, DATE(timestamp), timestamp;
```

The `channel_id NOT IN (...)` clause is omitted entirely when `excluded_channel_ids` is empty (SQLite rejects `NOT IN ()`). The `LIMIT` clause is omitted when `limit` is `None`. The inner query enforces the global recency cap; the outer reorders the kept rows for grouped rendering.

The bot user ID is read from `config.BOT_USER_ID`. The helper sits next to `get_raw_messages_24h` and `get_raw_messages_date_range` to keep all `raw_messages` queries in one neighborhood.

### `_build_system_prompt` change

In `bot.py`, after the `## User profile` block, append a new section. Pseudocode:

```python
excluded = (
    config.DEV_EXCLUDED_CHANNELS.split(",")
    if config.DEV_EXCLUDED_CHANNELS else []
)
rows = db_manager.get_recent_user_messages(
    server_id, days=3, limit=300, excluded_channel_ids=excluded
)
block = _format_activity_block(rows)
if block:
    system_prompt["content"] += f"\n\n## Recent guild activity (past 3 days)\n{block}"
```

A small private formatter `_format_activity_block(rows)` does the channel/day grouping and bullet rendering. It returns an empty string when `rows` is empty so the caller can skip the heading.

### `export_messages.py` refactor

The standalone script switches from inline SQL to calling `get_recent_user_messages`. It keeps its current behavior — 7-day window, no row cap (passes `limit=None`), excluding `cfmb` and `cfmb-dev`. The script resolves those two channel names to IDs once at startup with a `SELECT DISTINCT channel_id FROM raw_messages WHERE channel_name IN (?, ?)` query, then passes the resulting IDs to the helper.

## Configuration

No new configuration variables. Reuses:

- `BOT_USER_ID` — already loaded by `config.py`. Used to filter the bot's own posts.
- `DEV_EXCLUDED_CHANNELS` — already loaded as a comma-separated string of channel IDs. Currently contains only `cfmb-dev`. Splitting and passing to the helper means `#cfmb` user chatter is included in the context, which is the desired behavior (only the bot's own replies need to be excluded, and `user_id != BOT_USER_ID` already handles that).

## Sizing

Worst case: 300 messages × ~80 chars average content + ~30 chars overhead per line (username + bullet) ≈ **~33 KB** of prompt text. In practice, lower — many messages are short. The 300 cap is the only knob; raise or lower in code if needed.

## Error handling

The query is local SQLite. If it raises, the block is logged and skipped — the bot still replies. This mirrors the existing `## User profile` fallback, which substitutes a placeholder string when no profile exists.

The bot must never fail to reply because activity context could not be assembled.

## Testing

A new test in `test/` exercising `get_recent_user_messages`:

- Seed `raw_messages` with rows spanning before and after the 3-day cutoff, from multiple channels (including excluded ones), from the bot user and from other users.
- Assert the helper returns only non-bot rows, only from non-excluded channels, only within the window, in the correct order, and capped at `limit`.
- Edge cases: empty result, single-channel result, exactly-`limit` rows, more-than-`limit` rows.

No bot-integration test for `_build_system_prompt`'s new section — that path already has an existing test pattern using `AsyncMock` for Discord objects, and the new block is a thin formatter on top of the (tested) helper.

## Out of scope

- Per-channel caps or weighted sampling.
- Caching the result between mentions.
- Changing the export script's window or exclusion semantics.
- Surfacing the activity block to the user via `/context` or other introspection commands. Could be added later if useful.
