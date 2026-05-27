# Context Bot Redesign — Implementation Plan

**Goal:** Replace the current sprawling bot with a focused context bot per the spec. One trigger path (@mention or reply-to-bot), one LLM call per request, no tools, no scheduled tasks. System prompt assembled per request from a checked-in base file + freshly-fetched meetup/handbook + recent discord activity from other chains.

**Spec:** `docs/superpowers/specs/2026-05-23-context-bot-redesign.md`

**Tech stack:** Python 3.12, SQLite via stdlib `sqlite3`, `requests` + BeautifulSoup for web fetches, `ollama.AsyncClient` for LLM, pytest + pytest-asyncio + pytest-mock. Bot service managed via `systemctl --user`.

**Build order:** Helpers and new schema first, smoke test next so we can iterate on prompt shape against real data without an LLM, then the bot rewrite, then the demolition sweep. Each task ends in a green commit.

---

## File map

**Add:**
- `etc/base_system.md` — manually crafted base prompt.
- `cfmb/budget.py` — `len // 4` token cap helper.
- `cfmb/web_context.py` — meetup + handbook fetchers and markdown formatters.
- `cfmb/prompt.py` — pure assembly of system prompt + chain messages.
- `etc/smoke_prompt.py` — Layer 2 / Layer 3 smoke test driver.
- `test/test_db_manager.py` — replaces existing file, new schema.
- `test/test_budget.py`, `test/test_web_context.py`, `test/test_prompt.py` — new.

**Modify (in place, contents fully replaced where indicated):**
- `cfmb/db_manager.py` — new schema, slim query surface.
- `cfmb/llm_client.py` — strip to `__init__` + `get_completion`.
- `cfmb/config.py` — prune dead keys, add new ones.
- `cfmb/bot.py` — minimal rewrite, target <300 LoC.
- `requirements.txt` — drop `sqlite-vec`, `aiohttp`.

**Delete:**
- `cfmb/tools/` (whole directory).
- `cfmb/webfetch.py`.
- `etc/backfill_rag_chunks.py`, `etc/backfill_profiles.py`, `etc/backfill_summaries.py`.
- `static/communist_bugs_bunny.png`.
- `system.md` (replaced by `etc/base_system.md`).
- `test/test_bot.py` (replaced), `test/test_llm_client.py`, `test/test_webfetch.py`.

---

## Task 1: Seed `etc/base_system.md`

**Files:** Add `etc/base_system.md`.

- [ ] **Step 1:** Copy `system.md` to `etc/base_system.md`.
- [ ] **Step 2:** Strip the `Tool Use:` section (last two lines). Tools are gone.
- [ ] **Step 3:** Read it through. Confirm it's still coherent without the tool guidance. Tighten any awkward seams.
- [ ] **Step 4:** Commit.

```bash
git add etc/base_system.md
git commit -m "$(cat <<'EOF'
Add etc/base_system.md as the checked-in base system prompt

Seeded from system.md with tool-use guidance removed. Loaded into
memory once at bot startup; editing requires a restart.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Rewrite `cfmb/db_manager.py` for the new schema

The existing `db_manager.py` is replaced wholesale. The old bot.py will break — that's fine, it's getting rewritten in Task 10. All existing `db_manager` tests are obsolete; the test file is replaced in this task.

**Files:**
- Modify: `cfmb/db_manager.py` (full rewrite).
- Modify: `test/test_db_manager.py` (full rewrite).

- [ ] **Step 1:** Write the new test file first, against the schema and helpers from the spec:
  - `test_initialize_db` creates the `messages` table with the right columns + indexes.
  - `test_write_message_assigns_chain_id_on_mention` — message with `is_mention=True` gets `chain_id = message_id`.
  - `test_write_message_inherits_chain_from_reply` — reply to a row with a chain_id inherits it.
  - `test_write_message_reply_to_chainless_stays_null` — reply to a NULL-chain row keeps NULL.
  - `test_write_message_bot_reply_same_chain` — assistant-role writes use the supplied chain_id.
  - `test_get_chain_messages_ordered_oldest_first` — returns chain rows oldest-first with username/content/user_id.
  - `test_get_recent_discord_messages_filters` — past 7 days, server scope, excluded channels, `chain_id IS DISTINCT FROM <current>` (which keeps NULL-chain rows and rows from other chains, drops current-chain rows), newest-first.
  - `test_get_recent_discord_messages_handles_null_current_chain` — when there's no current chain (shouldn't really happen, but be safe), excludes nothing.

- [ ] **Step 2:** Implement `cfmb/db_manager.py`. Surface:

```python
class DatabaseManager:
    def __init__(self, db_path: str): ...
    def initialize_db(self) -> None: ...
    def write_message(
        self, *, server_id, message_id, user_id, username,
        channel_id, channel_name, content,
        reply_to_message_id: str | None,
        is_mention: bool,
        bot_user_id: str,
        chain_id_override: str | None = None,   # for explicit bot-reply writes
    ) -> str | None:
        """Resolves chain_id per the spec rules, writes the row, returns the chain_id."""
    def get_chain_messages(self, chain_id: str) -> list[dict]: ...
    def get_recent_discord_messages(
        self, server_id: str, current_chain_id: str | None,
        excluded_channel_ids: list[str], days: int = 7,
    ) -> list[dict]:
        """Returns rows ordered newest-first. Caller applies the token cap."""
    @contextmanager
    def _get_connection(self): ...
```

Schema init uses `CREATE TABLE IF NOT EXISTS` + index creation. No `ALTER TABLE` migration code — old schema is dropped, new bot starts on a fresh file.

- [ ] **Step 3:** Run `./test.sh -k test_db_manager`. Expect all pass.
- [ ] **Step 4:** Commit.

```bash
git add cfmb/db_manager.py test/test_db_manager.py
git commit -m "$(cat <<'EOF'
Rewrite db_manager for context-bot schema

One messages table with nullable chain_id replaces the prior split
between messages + raw_messages. Drop tables: system, user_profiles,
summaries, rag_chunks, message_embeddings, guild_points. write_message
resolves chain_id from reply target or @mention; get_chain_messages
returns the conversation thread; get_recent_discord_messages returns
candidate rows for the system-prompt discord section.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add `cfmb/budget.py`

**Files:**
- Add: `cfmb/budget.py`.
- Add: `test/test_budget.py`.

- [ ] **Step 1:** Write tests:
  - `test_cap_rows_drops_oldest_past_budget` — given rows newest-first, walks them, drops anything that would exceed the budget, returns the kept set in input order.
  - `test_cap_rows_empty_input_returns_empty`.
  - `test_cap_rows_all_fit_returns_all`.
  - `test_estimate_tokens_uses_div_4`.

- [ ] **Step 2:** Implement:

```python
PER_ROW_OVERHEAD = 8   # rough constant for bullet/timestamp formatting

def estimate_tokens(text: str) -> int:
    return len(text) // 4

def cap_rows(rows: list[dict], budget_tokens: int, content_key: str = "content") -> list[dict]:
    """Walks rows in input order, keeps as many as fit under the budget."""
    kept = []
    used = 0
    for row in rows:
        cost = estimate_tokens(row[content_key]) + PER_ROW_OVERHEAD
        if used + cost > budget_tokens:
            break
        kept.append(row)
        used += cost
    return kept
```

- [ ] **Step 3:** Run `./test.sh -k test_budget`. Expect green.
- [ ] **Step 4:** Commit.

```bash
git add cfmb/budget.py test/test_budget.py
git commit -m "$(cat <<'EOF'
Add cfmb/budget.py with len//4 token cap helper

estimate_tokens uses the spec-mandated len(text)//4 heuristic;
cap_rows walks an ordered list and keeps as many rows as fit under
the budget. Applied to raw row content before rendering, so the
formatted markdown is only approximately under cap.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add `cfmb/web_context.py`

**Files:**
- Add: `cfmb/web_context.py`.
- Add: `test/test_web_context.py` with HTML/JSON fixtures.

- [ ] **Step 1:** Write tests using fixture strings (no live network):
  - `test_format_meetup_events_renders_markdown` — feed a small list of event dicts, assert the markdown shape (title, date, location, URL).
  - `test_format_meetup_events_truncates_to_count` — respect `event_count`.
  - `test_html_to_markdown_strips_nav_and_chrome` — wiki HTML in, markdown out, no `<script>` / `<nav>` / inline styles.
  - `test_fetch_meetup_returns_empty_on_request_failure` — `requests.get` raises, function returns `""`.
  - `test_fetch_handbook_returns_empty_on_request_failure` — same.

- [ ] **Step 2:** Implement:

```python
def fetch_meetup_markdown(meetup_url: str, event_count: int) -> str:
    """Returns markdown of up to event_count upcoming events. Empty on failure."""

def fetch_handbook_markdown(handbook_url: str, token_budget: int) -> str:
    """Returns markdown of the handbook page truncated to budget. Empty on failure."""

def _format_meetup_events(events: list[dict], event_count: int) -> str: ...
def _html_to_markdown(html: str) -> str: ...
```

Meetup URL parsing: scrape the public events page (no API key). Fall back to empty string if the structure changes. Handbook: BS4 to text, strip nav/script/style elements before extracting.

- [ ] **Step 3:** Run `./test.sh -k test_web_context`. Expect green.
- [ ] **Step 4:** Manual smoke (no commit until passing): run a quick `python -c "from cfmb.web_context import fetch_meetup_markdown; print(fetch_meetup_markdown('<your meetup url>', 5))"` and eyeball.
- [ ] **Step 5:** Commit.

```bash
git add cfmb/web_context.py test/test_web_context.py
git commit -m "$(cat <<'EOF'
Add cfmb/web_context.py for per-request meetup + handbook fetches

Two pure functions: fetch_meetup_markdown(url, count) and
fetch_handbook_markdown(url, token_budget). Both return empty string
on failure so the per-request flow keeps working when external sites
are down. Synchronous requests.get is fine since the LLM queue
already serializes requests.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add `cfmb/prompt.py`

**Files:**
- Add: `cfmb/prompt.py`.
- Add: `test/test_prompt.py`.

- [ ] **Step 1:** Write tests:
  - `test_build_system_prompt_concatenates_sections` — base + meetup + handbook + discord, in order, with section headings.
  - `test_build_system_prompt_omits_empty_sections` — if `meetup` or `handbook` is `""`, skip the heading.
  - `test_render_discord_content_groups_channel_then_day` — multiple channels, multi-day, output uses `# {channel}` / `## {YYYY-MM-DD}` / `- {username}: {content}`.
  - `test_render_discord_content_collapses_whitespace`.
  - `test_build_chain_messages_derives_role_from_user_id` — `user_id == bot_user_id` → `assistant`, else `user`.
  - `test_build_chain_messages_orders_oldest_first`.

- [ ] **Step 2:** Implement:

```python
def render_discord_content(rows: list[dict]) -> str:
    """Renders discord-context rows (oldest-first within group) as markdown."""

def build_system_prompt(*, base: str, meetup: str, handbook: str, discord: str) -> str:
    """Concatenates the four sections with appropriate H2 headings, omitting empty sections."""

def build_chain_messages(rows: list[dict], bot_user_id: str) -> list[dict]:
    """Maps oldest-first chain rows to {'role', 'content'} dicts with role derived from user_id."""
```

- [ ] **Step 3:** Run `./test.sh -k test_prompt`. Expect green.
- [ ] **Step 4:** Commit.

```bash
git add cfmb/prompt.py test/test_prompt.py
git commit -m "$(cat <<'EOF'
Add cfmb/prompt.py for system prompt + chain assembly

Pure functions: render_discord_content groups rows by channel and
day, build_system_prompt concatenates base/meetup/handbook/discord
sections (skipping empty ones), build_chain_messages derives the
user/assistant role from user_id. Keeps bot.py focused on Discord
I/O rather than prompt shape.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Layer 2 smoke test (`etc/smoke_prompt.py`)

A one-shot script that reads `./cfmb_db.sqlite` (old schema, the copy we already have), builds a temp new-schema DB, accepts simulated incoming messages, prints the assembled prompt + chain to stdout.

**Files:** Add `etc/smoke_prompt.py`, add `etc/sim_messages.json` (small fixture).

- [ ] **Step 1:** Write the script. Outline:

```python
#!/usr/bin/env python3
"""Layer 2 smoke test: assemble system prompt from real data, no LLM."""
import argparse, json, sqlite3, sys
from pathlib import Path

from cfmb.db_manager import DatabaseManager
from cfmb.budget import cap_rows
from cfmb.prompt import (
    build_chain_messages, build_system_prompt, render_discord_content,
)
from cfmb.web_context import fetch_meetup_markdown, fetch_handbook_markdown
from cfmb.config import config

PROD_DB = Path(__file__).parent.parent / "cfmb_db.sqlite"
TMP_DB  = Path("/tmp/cfmb_smoke.sqlite")

def migrate_old_to_new(prod_db: Path, tmp_db: Path) -> None:
    """One-shot copy raw_messages rows into new messages, with chain_id from old messages."""
    if tmp_db.exists(): tmp_db.unlink()
    new = DatabaseManager(str(tmp_db))
    new.initialize_db()
    with sqlite3.connect(prod_db) as src:
        chains = dict(src.execute("SELECT message_id, chain_id FROM messages WHERE chain_id IS NOT NULL").fetchall())
        rows = src.execute(
            "SELECT server_id, message_id, user_id, username, channel_id, channel_name, content, timestamp "
            "FROM raw_messages WHERE message_id IS NOT NULL"
        ).fetchall()
    with sqlite3.connect(tmp_db) as dst:
        dst.executemany(
            "INSERT OR IGNORE INTO messages (server_id, message_id, chain_id, user_id, username, channel_id, channel_name, content, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(srv, mid, chains.get(mid), uid, uname, cid, cname, content, ts)
             for srv, mid, uid, uname, cid, cname, content, ts in rows],
        )

def run_simulated_message(db, sim, *, with_llm: bool) -> None:
    """For one simulated incoming message: resolve chain, assemble prompt, print (or send to LLM)."""
    # ... full pipeline, mirrors what bot.py will do ...
    print("=" * 80)
    print(f"SIMULATED: {sim['username']} in #{sim['channel']}: {sim['content']}")
    print("=" * 80)
    print("--- SYSTEM PROMPT ---")
    print(system_prompt)
    print("--- CHAIN MESSAGES ---")
    for m in chain_messages: print(f"[{m['role']}] {m['content']}")
    if with_llm:
        ...  # Layer 3 — added in Task 7

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-llm", action="store_true")
    parser.add_argument("--sim-file", default="etc/sim_messages.json")
    args = parser.parse_args()
    migrate_old_to_new(PROD_DB, TMP_DB)
    db = DatabaseManager(str(TMP_DB))
    sims = json.loads(Path(args.sim_file).read_text())
    for sim in sims:
        run_simulated_message(db, sim, with_llm=args.with_llm)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Write `etc/sim_messages.json` with 3–5 simulated messages — a fresh @mention, a reply-to-bot (use a real `message_id` from the prod sqlite that the bot once responded to), an @mention in a busy channel, an @mention referencing something specific you know was discussed recently.

- [ ] **Step 3:** Run `python etc/smoke_prompt.py`. Read the output. Iterate on:
  - `DISCORD_CONTENT_TOKEN_BUDGET` — start at 6000, watch what gets included.
  - `HANDBOOK_TOKEN_BUDGET` — start at 4000.
  - `MEETUP_EVENT_COUNT` — start at 5.
  - Tune section headings / formatting in `cfmb/prompt.py` if anything reads awkwardly.

Re-run until the prompt looks like something you'd want to send to an LLM. This step is iterative and has no fixed exit criterion — you stop when it looks good.

- [ ] **Step 4:** Commit.

```bash
git add etc/smoke_prompt.py etc/sim_messages.json
git commit -m "$(cat <<'EOF'
Add Layer 2 smoke test: assemble system prompt from real data

etc/smoke_prompt.py reads the copied prod sqlite (old schema), builds
a fresh new-schema DB in /tmp, replays a set of simulated incoming
messages through the full assembly pipeline, and prints the result
to stdout. Lets us iterate on prompt shape and section caps before
involving the LLM.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Layer 3 — `--with-llm` flag

**Files:** Modify `etc/smoke_prompt.py`.

- [ ] **Step 1:** Extend `run_simulated_message`: when `--with-llm` is set, build the `messages` list (`[{"role": "system", "content": system_prompt}, *chain_messages, {"role": "user", "content": sim['content']}]`) and call `LLMClient(config.OLLAMA_MODEL).get_completion(messages)`. Print the response under a `--- LLM RESPONSE ---` divider.
- [ ] **Step 2:** Run `python etc/smoke_prompt.py --with-llm`. Requires Ollama up locally with `OLLAMA_MODEL` available. Eyeball responses.
- [ ] **Step 3:** If responses are off, iterate on prompt shape / caps and re-run. Update `etc/base_system.md` here if the bot's voice needs tuning.
- [ ] **Step 4:** Commit when satisfied.

```bash
git add etc/smoke_prompt.py
git commit -m "$(cat <<'EOF'
Add Layer 3 smoke test: send assembled prompt through Ollama

--with-llm flag pipes the assembled prompt + simulated user message
to LLMClient.get_completion and prints the response. Catches
context-awareness issues eyeballing the prompt can't.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Rewrite `cfmb/llm_client.py`

**Files:**
- Modify: `cfmb/llm_client.py`.
- Delete: `test/test_llm_client.py` (only had one trivial test).

- [ ] **Step 1:** Replace the file contents:

```python
import sys, traceback
import ollama
from cfmb.config import config

def _llm_options() -> dict:
    return {
        "temperature": config.LLM_TEMPERATURE,
        "top_p": config.LLM_TOP_P,
        "top_k": config.LLM_TOP_K,
        "min_p": config.LLM_MIN_P,
        "presence_penalty": config.LLM_PRESENCE_PENALTY,
        "repeat_penalty": config.LLM_REPEAT_PENALTY,
    }

class LLMClient:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.async_client = ollama.AsyncClient()

    async def get_completion(self, messages: list[dict]) -> str | None:
        try:
            response = await self.async_client.chat(
                model=self.model_name, messages=messages, options=_llm_options(),
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"LLM error: {e}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            return None
```

- [ ] **Step 2:** Delete `test/test_llm_client.py`.
- [ ] **Step 3:** Run `./test.sh`. Expect green (existing new tests + nothing for llm_client).
- [ ] **Step 4:** Commit.

```bash
git add cfmb/llm_client.py
git rm test/test_llm_client.py
git commit -m "$(cat <<'EOF'
Strip LLMClient to get_completion only

Drop moderate, generate_image, get_completion_streaming, get_embedding,
and the tool-call loop. The redesigned bot makes one non-streaming
chat call per request with no tools.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Prune `cfmb/config.py`

**Files:** Modify `cfmb/config.py`. Modify `test/test_config.py` to drop assertions on removed keys.

- [ ] **Step 1:** Replace contents:

```python
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file="~/.cfmb", env_file_encoding="utf-8", extra="ignore")

    DISCORD_BOT_TOKEN: str
    OLLAMA_MODEL: str
    BOT_USER_ID: str
    DB_NAME: str
    DISCORD_MAX_MESSAGE_LENGTH: int
    DEV_CHANNEL_ID: int
    DEV_EXCLUDED_CHANNELS: str = ""

    MEETUP_URL: str
    HANDBOOK_URL: str
    MEETUP_EVENT_COUNT: int = 5
    HANDBOOK_TOKEN_BUDGET: int = 4000
    DISCORD_CONTENT_TOKEN_BUDGET: int = 6000
    CHAIN_TOKEN_BUDGET: int = 2000

    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.9
    LLM_TOP_K: int = 40
    LLM_MIN_P: float = 0.0
    LLM_PRESENCE_PENALTY: float = 0.0
    LLM_REPEAT_PENALTY: float = 1.1
    LLM_TIMEOUT_SECONDS: int = 300
    LLM_TIMEOUT_MESSAGE: str = "Sorry, I took too long to respond. Try again."

config = Config()
```

- [ ] **Step 2:** Update `test/test_config.py` to only assert on keys that survive.
- [ ] **Step 3:** Update your local `~/.cfmb`: add `HANDBOOK_URL`, optionally tune the new budget knobs; remove dead keys.
- [ ] **Step 4:** Run `./test.sh -k test_config`. Expect green.
- [ ] **Step 5:** Commit.

```bash
git add cfmb/config.py test/test_config.py
git commit -m "$(cat <<'EOF'
Prune config to context-bot keys; add new budget knobs

Drop: OLLAMA_EMBEDDING_MODEL, OLLAMA_IMAGE_MODEL, OLLAMA_FAST_MODEL,
BRAVE_SEARCH_API_KEY, SUMMARY_SYSTEM_PROMPT, CURATION_SYSTEM_PROMPT,
NEWSLETTER_CHANNEL_ID, NEWSLETTER_HOUR_ET, NEWSLETTER_TITLE,
ADMIN1/2/3_USER_ID, BOT_DISPLAY_NAME, NUM_CLOSEST_MESSAGES.

Add: HANDBOOK_URL, MEETUP_EVENT_COUNT, HANDBOOK_TOKEN_BUDGET,
DISCORD_CONTENT_TOKEN_BUDGET, CHAIN_TOKEN_BUDGET.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Rewrite `cfmb/bot.py`

**Files:**
- Modify: `cfmb/bot.py` (full rewrite, target <300 LoC).
- Delete: `test/test_bot.py` (replaced).
- Add: `test/test_bot.py` (small, focused on the two pieces that aren't pure helpers: `on_message` routing and `process_llm_request` orchestration).

- [ ] **Step 1:** Sketch the new `bot.py`:

```python
import asyncio, io, pathlib, sys
from datetime import timezone
from PIL import Image
import discord

from cfmb.config import config
from cfmb.db_manager import DatabaseManager
from cfmb.llm_client import LLMClient
from cfmb.budget import cap_rows, estimate_tokens
from cfmb.prompt import build_chain_messages, build_system_prompt, render_discord_content
from cfmb.web_context import fetch_meetup_markdown, fetch_handbook_markdown

ACTIVE_FILE = pathlib.Path("/tmp/cfmb_active")
BASE_PROMPT = pathlib.Path(__file__).parent.parent / "etc" / "base_system.md"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
db = DatabaseManager(config.DB_NAME)
llm = LLMClient(config.OLLAMA_MODEL)
llm_queue: asyncio.Queue = asyncio.Queue()
_base_prompt_text = ""

@client.event
async def on_ready():
    global _base_prompt_text
    db.initialize_db()
    _base_prompt_text = BASE_PROMPT.read_text()
    client.loop.create_task(llm_worker())
    print(f"Bot online as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user: return
    if message.guild is None:
        await message.channel.send("I can only respond in servers."); return

    reply_to = str(message.reference.message_id) if message.reference else None
    is_mention = client.user in message.mentions
    chain_id = db.write_message(
        server_id=str(message.guild.id),
        message_id=str(message.id),
        user_id=str(message.author.id),
        username=message.author.display_name,
        channel_id=str(message.channel.id),
        channel_name=message.channel.name,
        content=message.content,
        reply_to_message_id=reply_to,
        is_mention=is_mention,
        bot_user_id=str(config.BOT_USER_ID),
    )

    if is_mention or (reply_to and chain_id):
        await llm_queue.put((message, chain_id))

async def llm_worker():
    while True:
        message, chain_id = await llm_queue.get()
        try:
            ACTIVE_FILE.touch()
            await process_llm_request(message, chain_id)
        except Exception as e:
            print(f"LLM request error: {e}", file=sys.stderr)
        finally:
            ACTIVE_FILE.unlink(missing_ok=True)
            llm_queue.task_done()

async def process_llm_request(message, chain_id):
    server_id = str(message.guild.id)
    excluded = [c.strip() for c in config.DEV_EXCLUDED_CHANNELS.split(",") if c.strip()]
    discord_rows = db.get_recent_discord_messages(
        server_id=server_id, current_chain_id=chain_id,
        excluded_channel_ids=excluded, days=7,
    )
    discord_rows = cap_rows(discord_rows, config.DISCORD_CONTENT_TOKEN_BUDGET)
    discord_rows.reverse()  # render oldest-first within groups
    chain_rows = db.get_chain_messages(chain_id)
    chain_rows = cap_rows(list(reversed(chain_rows)), config.CHAIN_TOKEN_BUDGET)
    chain_rows.reverse()

    meetup = fetch_meetup_markdown(config.MEETUP_URL, config.MEETUP_EVENT_COUNT)
    handbook = fetch_handbook_markdown(config.HANDBOOK_URL, config.HANDBOOK_TOKEN_BUDGET)
    discord_md = render_discord_content(discord_rows)
    system_prompt = build_system_prompt(
        base=_base_prompt_text, meetup=meetup,
        handbook=handbook, discord=discord_md,
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(build_chain_messages(chain_rows, str(config.BOT_USER_ID)))

    image_bytes = await _extract_images(message)
    if image_bytes:
        messages[-1]["images"] = image_bytes

    async with message.channel.typing():
        async with asyncio.timeout(config.LLM_TIMEOUT_SECONDS):
            try:
                reply_text = await llm.get_completion(messages)
            except TimeoutError:
                reply_text = config.LLM_TIMEOUT_MESSAGE

    if not reply_text:
        await message.reply("Sorry, I encountered an error."); return
    reply = await message.reply(reply_text[: config.DISCORD_MAX_MESSAGE_LENGTH])
    db.write_message(
        server_id=server_id, message_id=str(reply.id),
        user_id=str(config.BOT_USER_ID), username=client.user.display_name,
        channel_id=str(message.channel.id), channel_name=message.channel.name,
        content=reply_text, reply_to_message_id=str(message.id),
        is_mention=False, bot_user_id=str(config.BOT_USER_ID),
        chain_id_override=chain_id,
    )

async def _extract_images(message) -> list[bytes]:
    out = []
    for att in message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            data = await att.read()
            if att.content_type == "image/gif":
                frame = Image.open(io.BytesIO(data)); frame.seek(0)
                buf = io.BytesIO(); frame.convert("RGB").save(buf, format="PNG")
                data = buf.getvalue()
            out.append(data)
    return out

if __name__ == "__main__":
    client.run(config.DISCORD_BOT_TOKEN)
```

- [ ] **Step 2:** Write a small new `test/test_bot.py` covering:
  - `test_on_message_ignores_self`
  - `test_on_message_ignores_dm`
  - `test_on_message_enqueues_on_mention`
  - `test_on_message_enqueues_on_reply_to_bot_chain`
  - `test_on_message_no_enqueue_for_plain_message`

  All with `AsyncMock`. Skip `process_llm_request` — it's covered by Layer 2/3 smoke tests.

- [ ] **Step 3:** Run `./test.sh`. Expect green across `test_db_manager`, `test_budget`, `test_web_context`, `test_prompt`, `test_config`, `test_bot`.
- [ ] **Step 4:** Re-run `python etc/smoke_prompt.py --with-llm`. Same output as before — bot rewrite shouldn't change prompt shape.
- [ ] **Step 5:** Commit.

```bash
git add cfmb/bot.py test/test_bot.py
git commit -m "$(cat <<'EOF'
Rewrite bot.py as context bot

One trigger path: @mention or reply-to-bot. One LLM call per request,
no tools, no scheduled tasks. System prompt assembled from
etc/base_system.md + per-request meetup/handbook fetches + recent
discord activity from other chains. chain_id resolved on every write.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Demolition sweep

**Files to delete:**

```bash
git rm -r cfmb/tools/
git rm cfmb/webfetch.py
git rm etc/backfill_rag_chunks.py etc/backfill_profiles.py etc/backfill_summaries.py
git rm static/communist_bugs_bunny.png
git rm system.md
git rm test/test_webfetch.py
```

**Files to edit:**

- [ ] **Step 1:** Remove `sqlite-vec` and (if no other use) `aiohttp` from `requirements.txt`.
- [ ] **Step 2:** Update `README.md` to reflect the new feature set — strip mentions of slash commands, RAG, newsletter; document `HANDBOOK_URL` and the budget knobs.
- [ ] **Step 3:** Update `CLAUDE.md` similarly — drop the references to RAG/profile/newsletter; describe the new architecture.
- [ ] **Step 4:** Run `./test.sh` one more time. Expect all green.
- [ ] **Step 5:** Commit.

```bash
git add -A
git commit -m "$(cat <<'EOF'
Demolition sweep: remove tools, RAG, scheduled tasks, slash commands

Delete cfmb/tools/, cfmb/webfetch.py, etc/backfill_*.py, the bugs-bunny
asset, system.md (replaced by etc/base_system.md), test_webfetch.py.
Strip sqlite-vec / aiohttp from requirements. Bring README and
CLAUDE.md in line with the new design.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Layer 4 — dev-server deploy

**Files:** none.

- [ ] **Step 1:** Push the branch to the remote.
- [ ] **Step 2:** On the prod host (`evilai@evilai`), pull the latest, **rename or move the existing `cfmb_db.sqlite`** so the new bot starts on a fresh DB (production data isn't migrated per the spec). Update `~/.cfmb` with `HANDBOOK_URL` and the new budget knobs.
- [ ] **Step 3:** `systemctl --user restart cfmb`. Check `journalctl --user -u cfmb -n 50` for the "Bot online" message.
- [ ] **Step 4:** In the dev Discord channel:
  - @mention the bot with a fresh message — confirm it replies and that the system prompt looks like what Layer 3 showed.
  - Reply to that bot reply with a follow-up — confirm chain continuity (it answers in context).
  - @mention again from an unrelated channel — confirm fresh chain, no contamination.
  - Drop an image with an @mention — confirm vision works.
  - Idle and wait 24h, then @mention again — confirm web fetches still work and discord content shows yesterday's activity.
- [ ] **Step 5:** If anything's off, drop into `journalctl --user -u cfmb -f`, find the failure, fix locally, re-cycle through tasks 7 → 12.
- [ ] **Step 6:** No commit — verification only.

---

## Self-review notes

- Spec coverage: schema (Task 2), web context (Task 4), token budget (Task 3), prompt assembly (Task 5), base prompt file (Task 1), bot rewrite (Task 10), llm_client trim (Task 8), config prune (Task 9), demolition (Task 11). Testing layers: unit (Tasks 2–5, 9, 10), Layer 2 smoke (Task 6), Layer 3 LLM smoke (Task 7), Layer 4 Discord (Task 12).
- Build order is reversible up through Task 10. Task 11 (demolition) is the point of no return — only run it after Layer 3 looks good.
- The smoke-test migration in Task 6 is one-shot prototyping code. It is not the production migration path; production starts on a fresh DB at Task 12.
- `_extract_images` in `bot.py` duplicates the GIF-handling logic from the current `process_llm_request`. Kept as-is since it works.
- `process_llm_request` is not unit-tested. It's covered by Layer 2/3 smoke tests against real data, which catches more than mock-based unit tests would.
- `cfmb_db.sqlite` (the copied prod DB) is already covered by `*.sqlite` in `.gitignore` — no action needed.
