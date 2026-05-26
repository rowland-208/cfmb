# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CFMB (Cape Fear Makers Bot) is a Discord context bot for the Cape Fear Makers Guild. It assembles a system prompt from a checked-in base file plus per-request meetup + handbook fetches plus past-week server activity, then sends one chat completion to OpenRouter (falling back to local Ollama). No tools, no slash commands, no scheduled tasks.

## Commands

**Run the bot locally:**
```bash
source venv-test/bin/activate
set -o allexport && source env/test.env && set +o allexport
python -m cfmb.bot
```

**Run all tests:**
```bash
./test.sh
```

**Restart the bot (systemd):**
```bash
systemctl --user restart cfmb
```

**Install dependencies (uses uv, not pip):**
```bash
uv pip install -r requirements.txt
uv pip install -r requirements-test.txt
```

**Migrate old-schema DB to the new schema (one-time, before first deploy):**
```bash
python etc/migrate.py --src cfmb_db.sqlite --dst cfmb.sqlite --bot-user-id <bot user id>
```

**Layer 2 / 3 smoke test (assemble system prompt against the dev sqlite):**
```bash
python etc/smoke_prompt.py                                          # Layer 2 (no LLM)
python etc/smoke_prompt.py --with-llm                               # Layer 3 (Ollama)
python etc/smoke_prompt.py --with-llm --openrouter <model:tag>      # Layer 3 (OpenRouter)
```

## Architecture

Python 3.12 package (`cfmb/`) with five modules:

- **bot.py** — `discord.Client`. `on_message` writes every message to the `messages` table, resolves `chain_id`, and enqueues an LLM request when the message is an @mention (user/role/everyone) or a reply to one of the bot's own messages. One LLM call per request, no streaming, no tools.
- **config.py** — Pydantic settings loaded from `~/.cfmb`. Required: `DISCORD_BOT_TOKEN`, `BOT_USER_ID`, `DB_NAME`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`. Sensible defaults for everything else (Ollama fallback model, token budgets, handbook URLs, sampler params).
- **db_manager.py** — SQLite abstraction. One table: `messages (id, server_id, message_id UNIQUE, chain_id NULLABLE, user_id, username, channel_id, channel_name, content, timestamp)`. `chain_id` is non-null only for messages that participate in a bot conversation (the @mention itself, replies that walked back to a chain, and the bot's own replies).
- **llm_client.py** — Calls OpenRouter via async HTTP first. On any failure (network, 4xx, 5xx), falls back to local Ollama via `ollama.AsyncClient`. Returns `None` if both backends fail.
- **prompt.py** — Pure assembly. `build_system_prompt(base, meetup, handbook, discord)` concatenates the four sections with `## H2` headings and `---` separators. `render_discord_content(rows)` groups by channel then by day. `build_chain_messages(rows, bot_user_id)` maps oldest-first chain rows to user/assistant turns, deriving the role from `user_id == BOT_USER_ID`.
- **web_context.py** — Per-request `fetch_meetup_markdown(url, event_count)` (reads `__NEXT_DATA__` from the events page, resolves Venue refs) and `fetch_handbook_markdown(urls, token_budget)` (BS4-strips chrome and pilcrows, walks `<template>` blocks for wiki.js content, accepts a list of URLs). Both return `""` on failure so the bot keeps working when external sites are down.
- **budget.py** — `cap_rows(rows, budget_tokens)` walks newest-first and keeps as many as fit using a `len(text)//4` token heuristic plus a per-row overhead constant.

Supporting:

- **etc/base_system.md** — Manually-crafted base prompt. Loaded once at process startup; edit + restart to update.
- **etc/migrate.py** — Standalone one-shot script to migrate an old-schema sqlite into the new schema.
- **etc/smoke_prompt.py** — Layer 2 / Layer 3 driver. Reads the local `cfmb_db.sqlite` (old schema), migrates into a temp new-schema DB, replays simulated incoming messages.

## Environment

Configuration lives in `~/.cfmb` (dotenv format), loaded by `python-dotenv` in `config.py` and by systemd's `EnvironmentFile=`.

**Required:** `DISCORD_BOT_TOKEN`, `BOT_USER_ID`, `DB_NAME`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`.

**Common overrides:** `OLLAMA_MODEL` (default `gemma3:4b`), `DEV_CHANNEL_ID`, `DEV_EXCLUDED_CHANNELS`, `MEETUP_URL`, `HANDBOOK_URLS`, `HANDBOOK_TOKEN_BUDGET`, `DISCORD_CONTENT_TOKEN_BUDGET`, `CHAIN_TOKEN_BUDGET`, `MEETUP_EVENT_COUNT`, `LLM_NUM_CTX`, the six Ollama sampler params, `LLM_TIMEOUT_SECONDS`, `LLM_TIMEOUT_MESSAGE`.

## Testing

Pytest with `pytest-asyncio` and `pytest-mock`. Database tests use temporary files. LLM-client tests mock both backends. Pure helpers (`prompt`, `budget`, `web_context`) have fixture-based unit tests. The `test/` directory only covers the new modules — the old test_bot/test_webfetch/test_llm_client suites were deleted with the modules they covered.

## Trigger rules

The bot responds when:
- The message @mentions the bot user, role, or everyone (`message.guild.me.mentioned_in(message)`), OR
- The message is a reply to a `messages` row whose `user_id == BOT_USER_ID`.

Otherwise the bot just writes the row to the DB and keeps watching.
