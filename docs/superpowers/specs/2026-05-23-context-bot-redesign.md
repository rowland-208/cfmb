# Context Bot Redesign — Design

## Goal

Replace the current sprawling feature set with a focused context bot. One trigger path (@mention or reply-to-bot), one LLM call per request, no tools, no scheduled tasks. The bot reads the room — recent server activity plus a freshly-fetched snapshot of official guild docs — and replies with awareness of both. It does not take actions beyond replying.

## Architecture

Four moving parts:

1. **One `messages` table.** `messages` and `raw_messages` collapse into a single table with nullable `chain_id`. Every Discord message the bot sees is written here.
2. **Base prompt on disk.** `etc/base_system.md` is the manually-crafted personality / guild-identity block. Loaded into memory once at process startup.
3. **Web context fetched per request.** Meetup events and the wiki handbook are scraped at request time, formatted to markdown, and concatenated. No scheduled task, no web-content cache table — the bot is rate-limited by Ollama, not by the network.
4. **Discord context built per request.** Past 7 days of messages from other chains, channel-grouped (sub-grouped by day), token-budgeted before rendering.

System prompt assembly order, every request: `base + web + discord`. Then the current chain's messages as user/assistant turns. Then the LLM call. That's it.

## Schema

One table:

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id    TEXT NOT NULL,
    message_id   TEXT NOT NULL UNIQUE,
    chain_id     TEXT,            -- NULL when not part of a bot conversation
    user_id      TEXT NOT NULL,
    username     TEXT,
    channel_id   TEXT,
    channel_name TEXT,
    content      TEXT,
    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_messages_chain ON messages (chain_id);
CREATE INDEX idx_messages_server_time ON messages (server_id, timestamp);
```

Role is derived: `user_id == config.BOT_USER_ID` → assistant, else user. No `role` column.

That is the entire persistent state. No `web_content`, `system`, `user_profiles`, `summaries`, `rag_chunks`, `guild_points`, or `message_embeddings`.

## chain_id assignment

On every incoming message, before writing:

1. If the message is a reply (`message.reference` is non-null), look up the referenced `message_id` in `messages`. If that row has a non-null `chain_id`, this message inherits it.
2. Else if the message @mentions the bot, this message starts a new chain — `chain_id = message_id`.
3. Else `chain_id` is NULL.

Bot replies are written with the same `chain_id` as the message that prompted them.

`chain_id IS NOT NULL` is the new "is this a bot conversation?" flag. The old `for_bot` boolean concept is implicit in chain membership.

## Trigger

The bot responds when:

- The message @mentions the bot (`client.user in message.mentions`), **or**
- The message is a reply to a `messages` row with `user_id == config.BOT_USER_ID`.

Both detections happen synchronously in `on_message`.

## Per-request flow

1. Resolve `chain_id` per the assignment rules; write the user's row.
2. If trigger fires, enqueue on `llm_queue`. Worker:
   1. Load `base` from in-memory cache (read once at startup).
   2. Fetch `meetup` events → format as markdown. On failure, render an empty section.
   3. Fetch `handbook` wiki page → HTML to markdown. On failure, render an empty section.
   4. Query candidate discord-content rows: past 7 days, `server_id = ?`, `channel_id NOT IN excluded`, `chain_id IS DISTINCT FROM <current_chain_id>`, ordered newest-first.
   5. Apply token budget **before formatting**: walk the candidate rows newest-first, summing `len(content) // 4` plus a small per-row overhead constant, drop anything past the budget. The remaining set is what gets rendered.
   6. Render the kept rows grouped by channel, sub-grouped by day, oldest-first within each group.
   7. Load current chain's messages oldest-first. Cap by the same `len // 4` heuristic against the chain budget, dropping oldest first. Map to user/assistant turns.
   8. Concatenate `base + meetup + handbook + discord` as one system message. Attach image bytes to the most recent user turn.
   9. Call `LLMClient.get_completion`. Reply on Discord. Write the bot's reply row with the chain id.

The LLM queue + worker survives — one request at a time keeps things sane against a single local Ollama instance.

## Token budgeting

`len(text) // 4` everywhere. Per-section budgets live in `~/.cfmb`:

- `DISCORD_CONTENT_TOKEN_BUDGET` (default tuned during prototyping)
- `CHAIN_TOKEN_BUDGET` (default tuned during prototyping)
- `HANDBOOK_TOKEN_BUDGET` (default tuned during prototyping)
- `MEETUP_EVENT_COUNT` (default 5)

Base prompt is whatever it is — assumed small. Total target is ~30K tokens (gemma3:12b context window minus a 2K output reserve), but the bot doesn't enforce a global cap; it enforces per-section caps and trusts the math.

Caps are applied to **raw row content** before rendering. The rendered markdown (headings, bullets, dates) adds overhead the budget doesn't precisely account for. That's acceptable — pad section budgets during prototyping to leave headroom for the formatting tax.

## Base prompt file

`etc/base_system.md` lives in the repo, checked in. Seeded from the existing `system.md` at repo root, with "Tool Use" / "Make heavy use of tools" stripped (tools are gone). Loaded into memory once at process startup. Editing it requires a restart — that's intentional, no `/set_system` command.

## Code to rip out

Aggressive deletion. Everything below goes:

- **Whole modules.** `cfmb/tools/`, `cfmb/webfetch.py`, all of `etc/backfill_*.py`, `static/communist_bugs_bunny.png`, `system.md` (replaced by `etc/base_system.md`).
- **All slash commands and their handlers.** `/help`, `/system`, `/set_system`, `/context`, `/preview`, `/profile`, `/profile_gen`, `/guildsearch`, `/websearch`, `/summary`, `/_summary`, `/debug`, `/exec`, `/bugs`, `/cfmb-set`.
- **All scheduled tasks.** `daily_newsletter`, `daily_summary`, `daily_profiles`, plus everything they call: `post_newsletter`, `generate_summary`, `_annotate_with_sources`, `_build_profile_prompt`, the dad-joke prompt.
- **All RAG infrastructure.** `RagBatcher`, `rag_chunks`, `message_embeddings`, `search_rag_chunks`, `write_rag_chunk`, `update_rag_chunk`, `get_latest_rag_chunk`, `get_embedding`.
- **Easter eggs and side features.** `NVDA` reaction, the entire emoji-reaction worker (`emoji_queue`, `emoji_worker_task`, `process_emoji_reaction`, `EMOJI_PATTERN`).
- **Streaming and thinking UX.** `_stream_llm`, `THINKING_STATUS_MESSAGES`, `_format_thinking`, the rotating status message logic, `get_completion_streaming`.
- **Moderation.** `LLMClient.moderate` and its prompt.
- **Image generation.** `LLMClient.generate_image`.
- **Fast/slow toggle.** No longer a thing.
- **Dead config keys.** `OLLAMA_EMBEDDING_MODEL`, `OLLAMA_IMAGE_MODEL`, `OLLAMA_FAST_MODEL`, `BRAVE_SEARCH_API_KEY`, `SUMMARY_SYSTEM_PROMPT`, `CURATION_SYSTEM_PROMPT`, `NEWSLETTER_CHANNEL_ID`, `NEWSLETTER_HOUR_ET`, `NEWSLETTER_TITLE`, `ADMIN1_USER_ID`, `ADMIN2_USER_ID`, `ADMIN3_USER_ID`, `BOT_DISPLAY_NAME`.
- **Dead tests.** Every test that exercises any of the above. `test_webfetch.py` goes entirely.

What survives in `bot.py`: `on_ready`, `on_message`, the LLM queue + worker, `chain_id` resolution, image-attachment handling, one LLM call site. Target under 300 LoC.

What survives in `db_manager.py`: schema init for the one table, `write_message`, `get_chain_for_message_id` (chain_id walker), `get_chain_messages`, `get_recent_discord_messages` (the past-7-day query with chain-exclusion). Target under 150 LoC.

What survives in `llm_client.py`: `__init__`, `get_completion`. Target under 50 LoC.

## Files to add

- `etc/base_system.md` (seeded from `system.md`).
- `cfmb/web_context.py` — pure functions `fetch_meetup_markdown()` and `fetch_handbook_markdown()`. Synchronous `requests.get` is fine; runs inside the queue worker, not the event loop. (We can wrap with `loop.run_in_executor` if it noticeably hurts mention responsiveness.)
- `cfmb/budget.py` — small helper for the `len // 4` cap.
- `cfmb/prompt.py` — pure assembly: `build_system_prompt(base, meetup, handbook, discord) -> str` and `build_chain_messages(rows) -> list[dict]`. Keeps `bot.py` focused on Discord I/O.

## Testing layers

Four layers, ordered cheapest to most expensive. Each layer is a precondition for the next.

### Layer 1 — Unit tests

Standard pytest. One file per pure helper.

- `db_manager`: chain_id resolution on insert (mention starts a chain; reply to chain-row inherits; reply to NULL stays NULL; bot reply gets the same chain_id), the past-7-day query (filters: server, excluded channels, chain dedup, time window, ordering).
- `cfmb/web_context.py`: HTML→markdown converter against fixture HTML; meetup event formatter against a small JSON fixture.
- `cfmb/budget.py`: walks rows newest-first, drops past the cap, returns the kept set in correct order.
- `cfmb/prompt.py`: section concatenation, empty-section handling, role derivation, chain-message ordering.

### Layer 2 — Prompt-generation smoke test (no LLM)

Goal: iterate on prompt shape using realistic data, without paying LLM latency or needing Ollama up.

A script (`etc/smoke_prompt.py`) that:

1. Reads from the copied production sqlite at `./cfmb_db.sqlite` (old schema).
2. Builds an in-memory or temp-file sqlite in the new schema. For each row in old `raw_messages`, write into new `messages`. For each message_id present in old `messages`, copy its `chain_id` over. Otherwise `chain_id` is NULL.
3. Accepts simulated incoming messages — either CLI args or a small JSON fixture file (`etc/sim_messages.json`) with `{channel, username, content, reply_to_message_id?}`.
4. For each simulated message, runs the full assembly pipeline (chain resolution, web fetches, discord query + cap, prompt build) and prints the assembled system prompt + chain messages to stdout with section dividers.

Output goes to stdout. Read it, eyeball it, tweak prompt or caps, rerun. This is where we tune `DISCORD_CONTENT_TOKEN_BUDGET`, `HANDBOOK_TOKEN_BUDGET`, `MEETUP_EVENT_COUNT`.

### Layer 3 — LLM-in-the-loop smoke test

Same script with a `--with-llm` flag. After printing the assembled prompt, sends it to Ollama and prints the response. Requires Ollama running locally with `OLLAMA_MODEL` available.

This catches things eyeballing can't — does the model actually use the context, does it get confused by the discord-content section, do replies feel guild-aware.

### Layer 4 — Discord integration

Deploy to the dev server (the second `server_id` already in our dev sqlite). @mention the bot, reply to it, mention it again from a fresh thread. Check that chain_id flows correctly, that the system prompt assembles, that responses arrive within the LLM timeout.

Only after Layer 3 looks good. Layer 4 is for catching Discord-specific issues — reply detection, message-content intent, attachment handling.

## Out of scope

- Migrating data from old `messages` / `raw_messages` into the new schema for production. Dev keeps the copied sqlite for iteration; production starts fresh after deploy. The week of lost context isn't worth the migration code.
- In-memory caching of web fetches between requests. Premature; revisit only if request latency becomes a complaint.
- Per-channel discord-content quotas. Past-7-day + global token cap is the only knob.
- Surface for editing `base_system.md` without a redeploy. Edit and `systemctl --user restart cfmb`.
