# CFMB System Inventory

A flat catalog of every feature, component, and code branch in the bot as of `main` (commit `2722ed2`). Each heading is one unit. Used, partially-used, and dead branches are all listed and labeled so the overhaul can make decisions about each in turn.

Totals: ~2,235 LoC of Python across 10 files. One module (`bot.py`) holds ~1,120 of those lines.

---

## Discord event entry: `on_ready`

`bot.py:82`. Initializes the SQLite database, starts the LLM worker task, starts the (disabled) emoji-reaction worker task, starts the three `discord.ext.tasks` loops (`daily_newsletter`, `daily_profiles`, `daily_summary`), and posts a "Restart success!" announcement in `DEV_CHANNEL_ID`. Effectively the wiring point that turns the static module-level singletons (`client`, `db_manager`, `llm_client`, `llm_queue`, `rag_batcher`) into a running system.

## Discord event entry: `on_message`

`bot.py:233`. The single dispatcher for every message the bot sees. In order, it: (1) drops self-messages and DMs, (2) writes the raw row to `raw_messages`, (3) schedules a `RagBatcher.add_message` task, (4) resolves a reply-chain id, (5) does a hard-coded `"NVDA"` substring reaction, (6) **was** going to enqueue an emoji reaction but that line is commented out, (7) routes on `/command` prefixes to a long if/elif ladder, (8) falls through to `handle_bot_mention` if the bot was @mentioned. Every new "trigger condition" the user wants would land here.

## Trigger: `@mention`

`bot.py:333`. The only LLM trigger besides `/debug`. Calls `handle_bot_mention`, which puts the message on `llm_queue`. There is no other built-in trigger (no keyword wake words, no thread auto-follow, no first-post-in-channel handler, no scheduled "say something interesting" loop).

## Trigger: reply-chain continuation

`bot.py:794` (`resolve_chain_id`). When a user replies to a message the bot has seen, `resolve_chain_id` walks the `messages.message_id → chain_id` mapping to keep the conversation context coherent across replies. This is the only mechanism for thread/reply continuity — the bot has no concept of Discord threads as first-class entities, only reply chains.

## Trigger: hard-coded `NVDA` reaction

`bot.py:267`. If a message contains the substring `NVDA`, the bot adds a 👀 reaction. Pure string match, no LLM call. Vestigial easter egg.

## Trigger: scheduled tasks (3)

Three `@tasks.loop(time=…)` decorators in `bot.py`: `daily_newsletter` at `NEWSLETTER_HOUR_ET:00` ET, `daily_profiles` at 04:00 ET, `daily_summary` at 05:00 ET. Each independently fetches `NEWSLETTER_CHANNEL_ID`, derives `server_id` from its guild, and runs its respective pipeline. There is no shared scheduler abstraction — each is its own `@tasks.loop`.

## Feature: LLM queue + `llm_worker`

`bot.py:62, 735`. An `asyncio.Queue` and a single consumer task that processes one LLM request at a time, touching `/tmp/cfmb_active` while busy so `update.sh` knows to defer restarts. This is what serializes mention responses; without it, parallel mentions would step on each other on the local Ollama instance.

## Feature: streaming with thinking + tool calls (`_stream_llm` + `process_llm_request`)

`bot.py:916, 1008`. The full @mention pipeline: resolves mentions, optionally moderates, writes the user turn, attaches images, fetches the first URL in the message, builds the system prompt, looks up tools, posts a rotating "thinking..." status message, calls `llm_client.get_completion_streaming` with a tool handler, optionally streams thinking-chunks back to Discord (for `/debug`), and finally replies and persists the assistant turn. About 200 LoC for one path — the biggest single unit in the codebase.

## Feature: status-message cycling

`bot.py:872, 1070`. A list of ~40 flavored "thinking..." strings (`THINKING_STATUS_MESSAGES`) and an `asyncio.Task` that edits the reply message every 7 seconds to cycle through them while the LLM is busy. Pure UX; deletes the status on success or timeout.

## Feature: image attachment handling

`bot.py:1026`. Reads image attachments off the message, converts GIFs to PNG (first frame only via PIL), and attaches the resulting bytes as `images` on the final user-turn message. Wired into the streaming completion call.

## Feature: URL extraction → webfetch context injection

`bot.py:1046` calling `cfmb/webfetch.py`. If the user's message contains an HTTP(S) URL, `extract_first_url` + `get_webpage_text` fetch the page, `BeautifulSoup`-clean it, and append the text as a synthetic `{"role": "tool"}` message to the LLM context. No truncation, no caching, blocking `requests.get`.

## Feature: moderation pass

`bot.py:1015, llm_client.py:53` (`LLMClient.moderate`). A separate `chat()` call asking the same model to return `allow` or `block`. The hand-tuned system prompt includes "manipulation attempt" examples. **Currently bypassed:** the call site passes `skip_moderation=True` for both the @mention path and the `/debug` path — so the feature exists but is dead in production.

## Feature: system prompt assembly (`_build_system_prompt`)

`bot.py:821`. Pulls the server's stored system prompt, appends a `## Metadata` block (channel, user, current time, "user last active"), then appends a `## User profile` block (either the latest persisted profile or a "still learning" placeholder). The recent-guild-activity injection from the May 2 spec is **not yet implemented** — only the spec and plan markdown exist in `docs/superpowers/`.

## Feature: tools framework

`cfmb/tools/__init__.py:1` + `cfmb/tools/base.py`. A small plugin registry: `Tool` is an ABC with `name`, `description`, `parameters`, `enabled()`, `run(args, context)`, and `schema()`. `__init__.py` walks `pkgutil.iter_modules` at first call, instantiates every `Tool` subclass, and exposes `get_tools()` / `get_tool(name)`. The bot wires this into the streaming call so the LLM can call any enabled tool by name.

## Tool: `guildsearch`

`cfmb/tools/guildsearch.py`. Calls `LLMClient.get_embedding`, then `db_manager.search_rag_chunks` with a 720-hour (30-day) window, returns the top 3 chunks rendered as `[#channel]\n<content>`. Disabled when `OLLAMA_EMBEDDING_MODEL` is unset. Note the file re-implements `_resolve_mentions` locally — same function also lives in `bot.py`.

## Tool: `websearch`

`cfmb/tools/websearch.py`. Brave Search API call, top 5 web results formatted as `**title**\nurl\ndescription`. Requires `BRAVE_SEARCH_API_KEY`.

## Slash command: `/help`

`bot.py:711`. Static text help listing commands. Out of date — does not mention `/websearch`, `/bugs`, `/exec`, `/preview`, `/_summary`, or `/cfmb-set` consistently.

## Slash command: `/system`

`bot.py:363`. Echoes the current per-server system prompt from the `system` table.

## Slash command: `/set_system`

`bot.py:370`. Writes a new system prompt to the `system` table for this server. No permission check — anyone can set it.

## Slash command: `/context`

`bot.py:339`. Prints the last 4 chain_ids and up to 6 messages each, with snippets. Debugging aid for the reply-chain RAG model.

## Slash command: `/preview`

`bot.py:394`. Runs `_build_system_prompt` against a hypothetical user message and dumps the result in 1950-char chunks. Lets you inspect what the bot would see without burning an LLM call.

## Slash command: `/profile`

`bot.py:441`. Fetches the most recent stored profile for the mentioned user (or self) from `user_profiles`.

## Slash command: `/profile_gen`

`bot.py:412`. Generates a profile on the fly from the past 7 days of the target user's messages. Does **not** persist — read/write asymmetry with `/profile`. Requires 20+ messages.

## Slash command: `/guildsearch`

`bot.py:455`. CLI front door for the `guildsearch` RAG tool. Returns 3 chunks with a discord.com deep-link `[jump]` and a percent-match score.

## Slash command: `/websearch`

`bot.py:488`. CLI front door for the Brave Search tool.

## Slash command: `/summary`

`bot.py:529`. Runs `post_newsletter` on demand — same pipeline as the scheduled daily newsletter.

## Slash command: `/_summary`

`bot.py:508`. The "key facts" pipeline (`generate_summary`) printed back to the channel as `>>>` quote blocks split on `---`. Different from `/summary` (which is the newsletter). The underscore-prefixed name suggests it was meant as a debug command.

## Slash command: `/debug`

`bot.py:328`. Strips the prefix and runs `handle_bot_mention` with `save_thinking=True`, which streams the LLM's thinking text back to the channel in quote-block chunks plus a `🔧 Tool: <name>` block for every tool call.

## Slash command: `/exec`

`bot.py:377`. Runs an arbitrary shell command on the host and returns stdout/stderr. Gated to `ADMIN2_USER_ID` and `ADMIN3_USER_ID` only. `ADMIN1_USER_ID` is loaded by `config.py` but referenced nowhere — silently dead.

## Slash command: `/bugs` — **broken**

`bot.py:272, 670`. Handler imports `cfmb.tools.bugs` at call time. That module was deleted in commit `0f530f8` ("Remove bugs meme tool; no longer commie"), but the dispatcher line and the handler function are still in `bot.py`. Calling `/bugs` will raise `ModuleNotFoundError`.

## Slash command: `/cfmb-set`

`bot.py:684`. Switches `llm_client.model_name` between `OLLAMA_MODEL` (slow, thinking on) and `OLLAMA_FAST_MODEL` (fast, thinking off). With no arg, prints the current mode. Mutates the live singleton — survives until restart.

## Pipeline: daily newsletter (`post_newsletter`)

`bot.py:538`. Per-channel: build a transcript, call `SUMMARY_SYSTEM_PROMPT` to summarize, collect blocks. Then call `CURATION_SYSTEM_PROMPT` over the joined blocks to produce the curated newsletter. Then optionally annotate inline with `[N]` source links via `_annotate_with_sources` (RAG-backed). Finally generate a one-liner dad joke against the curated text and post it. ~100 lines, three LLM calls per channel plus one curation call plus one dad-joke call plus per-segment annotation calls.

## Pipeline: RAG source annotation (`_annotate_with_sources`)

`bot.py:645`. Splits the curated newsletter on punctuation, embeds each 5+ word segment, finds the closest `rag_chunks` row from the past 24 hours, and if the cosine distance is under 0.408 inserts an inline numbered footnote-link to the original discord message. Distance threshold is a magic number. Runs sequentially, one embedding per segment.

## Pipeline: daily summary (`daily_summary` + `generate_summary`)

`bot.py:107, 162`. Pulls the past 24h of `raw_messages`, groups by channel, joins them, and asks the LLM for "the five most important facts" in a strict format (`what:` / `users:` / `channel:` / `---`). Saves to the `summaries` table. **Originally pitched as a RAG replacement; not currently used as context by any other path** — `get_recent_summaries` exists in `db_manager.py` but has no caller.

## Pipeline: daily profiles (`daily_profiles` + `_build_profile_prompt`)

`bot.py:178, 203`. For every user with 20+ messages in the past 7 days, build a per-user transcript, call the LLM with the profile template, and store the result in `user_profiles`. Consumed by `_build_system_prompt` on every @mention.

## Pipeline: RAG batching (`RagBatcher`)

`bot.py:30`. Real-time, on every incoming message. Per channel, append the formatted line to the latest `rag_chunks` row if its content is under 512 chars, capped at 2048; otherwise start a new chunk. Each write re-embeds the entire chunk content via `LLMClient.get_embedding`. Side effect of `on_message`, never awaited (`asyncio.ensure_future`). Disabled when `OLLAMA_EMBEDDING_MODEL` is unset.

## Pipeline: emoji reactions (`process_emoji_reaction`) — **disabled**

`bot.py:751, 765`. A second worker that asks the LLM to pick a one-character emoji (~1% rate, 10% if "excited") with a comma-separated palette favoring communist symbols. The enqueue line in `on_message` is commented out with "temporarily disabled for debugging" (line 270). The worker task is still started in `on_ready` but its queue is never fed.

## Component: `cfmb/config.py`

41 lines, one `Config(BaseSettings)` class loading from `~/.cfmb`. Roughly 30 settings: discord, ollama models (`OLLAMA_MODEL`, `OLLAMA_FAST_MODEL`, `OLLAMA_IMAGE_MODEL`, `OLLAMA_EMBEDDING_MODEL`), admins, RAG/newsletter knobs, six raw LLM sampler params (`LLM_TEMPERATURE` … `LLM_REPEAT_PENALTY`), Brave key, timeout settings. Loaded once at import time into a module-level `config` singleton.

## Component: `cfmb/llm_client.py`

245 lines. Wraps `ollama.AsyncClient`. Methods: `generate_image` (POST to `/api/generate` — **never called from bot.py**), `moderate` (called but bypassed), `get_completion` (non-streaming with tool loop — used by every scheduled pipeline), `get_completion_streaming` (streaming with tool loop and per-chunk callbacks — used only by `@mention` / `/debug`), `get_embedding`. The two completion methods duplicate the same tool-call loop logic.

## Component: `cfmb/db_manager.py` — schema (7 tables)

608 lines. SQLite via stdlib `sqlite3` plus the `sqlite_vec` extension loaded per-connection. Tables created on first run via `IF NOT EXISTS` + a long list of `ALTER TABLE ADD COLUMN` migration attempts wrapped in `try/except OperationalError`. The seven tables: `messages` (LLM context per chain), `system` (per-server system prompt history), `guild_points` (member point ledger — **unused**), `raw_messages` (every Discord message), `user_profiles` (per-user nightly profile snapshots), `summaries` (daily key-facts), `rag_chunks` (embedded message batches per channel).

## Component: `cfmb/db_manager.py` — query surface

About 25 public methods. Roughly clusters into: per-server system prompt I/O, chain/message I/O for the LLM context, raw-message readers with several time windows (24h, 7d, date range, by-user 7d, by-user N), user-id-to-name mapping, profile read/write, RAG chunk read/write/search, summary read/write, and member-points read/write. **Three entire groups are dead code:** guild_points (no caller), `get_recent_summaries` (no caller), `get_recent_raw_messages_by_user` (no caller). All methods swallow `sqlite3.Error` and return a falsy default — failures are invisible except in stdout.

## Component: `cfmb/webfetch.py`

58 lines. `get_webpage_text(url)` returns BS4-cleaned text; `extract_first_url(text)` regex-matches the first URL. Called once per @mention from `process_llm_request`. Blocking `requests.get` runs on the event loop.

## Auxiliary: backfill scripts (3)

`etc/backfill_rag_chunks.py` (rebuild `rag_chunks` from the past N days of `raw_messages`), `etc/backfill_profiles.py`, `etc/backfill_summaries.py`. Run manually after schema changes or model swaps. They import `cfmb.db_manager` directly and bypass the bot.

## Auxiliary: deployment scripts

`main.sh` (creates `venv-main`, installs deps, sources `env/main.env`, runs `python -m cfmb.bot`), `update.sh` (cron-driven `git pull` + restart, defers when `/tmp/cfmb_active` exists), `test.sh` (sets up venv, sources test env, runs pytest). Systemd `cfmb.service` lives in `~/.config/systemd/user/` (per README).

## Tests

`test/` has 5 files covering `bot`, `config`, `db_manager`, `llm_client`, `webfetch`. About 35 test functions. Coverage is shallow: `test_bot.py` covers the trivial command handlers (`/system`, `/set_system`, `/exec`, `/help`) and chain-id resolution, but **none of `process_llm_request`, `_stream_llm`, `_build_system_prompt`, `RagBatcher`, any scheduled task, or any tool**. `test_llm_client.py` is a single `__init__` test. This is the "mostly untestable" the user mentioned: the long async functions in `bot.py` mix Discord I/O, DB writes, LLM calls, and queue scheduling in one body.

## Vestigial / dead code summary

Calling these out explicitly because the overhaul will want to choose which to delete vs. revive:

- `/bugs` command — handler still wired, module deleted, will crash on invocation.
- `process_emoji_reaction` worker — task is started, enqueue is commented out.
- `generate_image` in `LLMClient` and `OLLAMA_IMAGE_MODEL` config — never invoked.
- `add_member_points` / `get_member_points` / `guild_points` table — no caller.
- `get_recent_summaries` — `summaries` table is written nightly but never read back.
- `get_recent_raw_messages_by_user` — no caller.
- `ADMIN1_USER_ID` — loaded but unreferenced; `/exec` only checks ADMIN2/3.
- `_resolve_mentions` — duplicated in `cfmb/bot.py` and `cfmb/tools/guildsearch.py`.
- `docs/superpowers/specs/2026-05-02-recent-guild-activity-context-design.md` + matching plan — design landed, code did not.
- Daily summary pipeline — runs, persists, but no downstream consumer in any context-building path.
