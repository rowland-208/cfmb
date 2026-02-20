# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CFMB (Cape Fear Makers Bot) is a Discord bot for the Cape Fear Makers Guild. It integrates with Ollama for local LLM inference, uses SQLite for persistence, and supports web scraping for context enrichment.

## Commands

**Run the bot:**
```bash
./main.sh
```

**Run all tests:**
```bash
./test.sh
```

**Run tests using test.sh** (sets up venv and env vars automatically):
```bash
./test.sh
```

**Install dependencies (uses uv, not pip):**
```bash
uv pip install -r requirements.txt
uv pip install -r requirements-test.txt
```

## Architecture

The bot is a Python 3.12 package (`cfmb/`) with five modules:

- **bot.py** — Discord event handlers and command dispatch. Entry point via `python -m cfmb.bot`. Commands are prefixed with `!` (e.g., `!help`, `!system`, `!points`). The bot also responds to @mentions via Ollama.
- **config.py** — Pydantic-based settings loaded from environment files in `env/`. Validates and coerces types for all config values.
- **db_manager.py** — SQLite abstraction with context managers for connections. Three tables: `messages` (conversation history per server), `system` (per-server system prompts), `guild_points` (user points tracking).
- **llm_client.py** — Async wrapper around Ollama's `AsyncClient`. `get_completion` is an async method so it doesn't block the event loop. Returns `None` on errors.
- **webfetch.py** — Extracts URLs from messages, fetches pages with BeautifulSoup, returns cleaned text content.

## Environment

Configuration lives in `env/` with separate files for main, test, and dev environments. Required variables include `DISCORD_BOT_TOKEN`, `OLLAMA_MODEL`, `BOT_USER_ID`, `DB_NAME`, `CONTEXT_SIZE`, `ADMIN1_USER_ID`, and `ADMIN2_USER_ID`.

## Testing

Tests use pytest with pytest-asyncio and pytest-mock. Bot tests use `AsyncMock` for Discord objects. Database tests use temporary files for isolation. The test environment uses `env/test.env` for configuration.
