#!/usr/bin/env python3
"""Layer 2 / Layer 3 smoke test.

Reads the copied prod sqlite at ./cfmb_db.sqlite (old schema), migrates to a
fresh new-schema DB at /tmp/cfmb_smoke.sqlite, replays simulated incoming
messages through the full assembly pipeline, and prints the assembled prompt
to stdout.

Layer 2 (default): no LLM call.
Layer 3 (--with-llm): also sends the assembled prompt through Ollama and
    prints the response.

Tune token budgets via flags; iterate on prompt shape via cfmb/prompt.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cfmb.budget import cap_rows, estimate_tokens
from cfmb.db_manager import DatabaseManager
from cfmb.prompt import (
    build_chain_messages, build_system_prompt, render_discord_content,
)
from cfmb.web_context import fetch_handbook_markdown, fetch_meetup_markdown


PROD_DB = REPO_ROOT / "cfmb_db.sqlite"
TMP_DB = Path("/tmp/cfmb_smoke.sqlite")
BASE_PROMPT_PATH = REPO_ROOT / "etc" / "base_system.md"

DEFAULT_MEETUP_URL = "https://www.meetup.com/cfmakers/events/?type=upcoming"
DEFAULT_HANDBOOK_URLS = [
    "https://wiki.capefearmakersguild.org/makerspace-rules",
    "https://wiki.capefearmakersguild.org/personnel",
    "https://wiki.capefearmakersguild.org/en/machines/bambu-3d-printers",
    "https://wiki.capefearmakersguild.org/en/machines/carvera-cnc",
    "https://wiki.capefearmakersguild.org/en/machines/omtech-co2-laser",
    "https://wiki.capefearmakersguild.org/en/machines/omtech-fiber-laser",
]


def migrate_old_to_new(prod_db_path: Path, tmp_db_path: Path, bot_user_id: str) -> None:
    """One-shot copy of prod data into the new schema.

    Strategy:
    - Build {message_id: chain_id} map from old `messages` table.
    - Copy old `raw_messages` rows into new `messages`, attaching chain_id.
    - Additionally copy old `messages` rows where role='assistant' and
      message_id is not null, with user_id = bot_user_id, so the migrated DB
      contains bot replies and chains look complete.
    """
    if tmp_db_path.exists():
        tmp_db_path.unlink()
    new = DatabaseManager(str(tmp_db_path))
    new.initialize_db()

    src = sqlite3.connect(prod_db_path)
    src.row_factory = sqlite3.Row

    chains: dict[str, str] = {}
    for row in src.execute(
        "SELECT message_id, chain_id FROM messages "
        "WHERE chain_id IS NOT NULL AND message_id IS NOT NULL"
    ):
        chains[row["message_id"]] = row["chain_id"]

    raw_rows = src.execute(
        "SELECT server_id, message_id, user_id, username, channel_id, channel_name, "
        "content, timestamp FROM raw_messages WHERE message_id IS NOT NULL ORDER BY id ASC"
    ).fetchall()

    bot_rows = src.execute(
        "SELECT chain_id, message_id, content, channel_id, channel_name, timestamp "
        "FROM messages WHERE role='assistant' AND message_id IS NOT NULL"
    ).fetchall()

    src.close()

    dst = sqlite3.connect(str(tmp_db_path))
    raw_inserted = 0
    for r in raw_rows:
        dst.execute(
            "INSERT OR IGNORE INTO messages (server_id, message_id, chain_id, user_id, "
            "username, channel_id, channel_name, content, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["server_id"], r["message_id"], chains.get(r["message_id"]),
             r["user_id"] or "unknown", r["username"], r["channel_id"],
             r["channel_name"], r["content"] or "", r["timestamp"]),
        )
        raw_inserted += dst.total_changes - raw_inserted

    bot_inserted = 0
    for r in bot_rows:
        # Bot rows in old `messages` typically share server_id with raw rows in
        # the same chain — try to infer one.
        server_id_row = dst.execute(
            "SELECT server_id FROM messages WHERE chain_id = ? LIMIT 1",
            (r["chain_id"],),
        ).fetchone()
        server_id = server_id_row[0] if server_id_row else "unknown"
        dst.execute(
            "INSERT OR IGNORE INTO messages (server_id, message_id, chain_id, user_id, "
            "username, channel_id, channel_name, content, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (server_id, r["message_id"], r["chain_id"], bot_user_id, "bot",
             r["channel_id"], r["channel_name"], r["content"] or "", r["timestamp"]),
        )
        bot_inserted += 1
    dst.commit()
    dst.close()
    print(f"Migrated: {raw_inserted} raw rows, {bot_inserted} bot rows → {tmp_db_path}",
          file=sys.stderr)


def _call_openrouter(messages: list[dict], model: str, api_key: str) -> str:
    """One-shot OpenAI-compatible chat completion via OpenRouter."""
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def process_sim(
    db: DatabaseManager,
    sim: dict,
    *,
    base_text: str,
    discord_budget: int,
    chain_budget: int,
    handbook_budget: int,
    meetup_count: int,
    meetup_url: str,
    handbook_urls: list[str],
    bot_user_id: str,
    no_web: bool,
    with_llm: bool,
    openrouter_model: str | None,
    now_iso: str | None,
) -> None:
    chain_id = db.write_message(
        server_id=sim["server_id"], message_id=sim["message_id"],
        user_id=sim["user_id"], username=sim["username"],
        channel_id=sim["channel_id"], channel_name=sim["channel"],
        content=sim["content"],
        reply_to_message_id=sim.get("reply_to_message_id"),
        is_mention=bool(sim.get("is_mention", False)),
        bot_user_id=bot_user_id,
    )

    excluded = sim.get("excluded_channel_ids", [])
    discord_rows_newest_first = db.get_recent_discord_messages(
        server_id=sim["server_id"], current_chain_id=chain_id,
        excluded_channel_ids=excluded, days=7, now_iso=now_iso,
    )
    kept_newest_first = cap_rows(discord_rows_newest_first, discord_budget)
    discord_rows = list(reversed(kept_newest_first))

    chain_rows_oldest_first = db.get_chain_messages(chain_id) if chain_id else []
    capped_newest_first = cap_rows(list(reversed(chain_rows_oldest_first)), chain_budget)
    chain_rows = list(reversed(capped_newest_first))

    if no_web:
        meetup_md = ""
        handbook_md = ""
    else:
        meetup_md = fetch_meetup_markdown(meetup_url, meetup_count)
        handbook_md = fetch_handbook_markdown(handbook_urls, handbook_budget)

    discord_md = render_discord_content(discord_rows)
    system_prompt = build_system_prompt(
        base=base_text, meetup=meetup_md, handbook=handbook_md, discord=discord_md,
    )
    chain_messages = build_chain_messages(chain_rows, bot_user_id)

    print("=" * 80)
    print(f"SIMULATED: {sim['username']} in #{sim['channel']}: {sim['content']!r}")
    print(f"chain_id: {chain_id}")
    print(f"discord rows kept: {len(discord_rows)} of {len(discord_rows_newest_first)}")
    print(f"chain rows kept:   {len(chain_rows)} of {len(chain_rows_oldest_first)}")
    print("=" * 80)
    print("--- SYSTEM PROMPT ---")
    print(system_prompt)
    print()
    print("--- CHAIN MESSAGES ---")
    for m in chain_messages:
        print(f"[{m['role']}] {m['content']}")
    print()
    print("--- TOKEN ESTIMATES ---")
    sys_tokens = estimate_tokens(system_prompt)
    chain_tokens = sum(estimate_tokens(m["content"]) for m in chain_messages)
    print(f"system: ~{sys_tokens} tokens")
    print(f"chain:  ~{chain_tokens} tokens")
    print(f"total:  ~{sys_tokens + chain_tokens} tokens")

    if with_llm:
        print()
        messages = [{"role": "system", "content": system_prompt}, *chain_messages]
        if openrouter_model:
            print(f"--- LLM RESPONSE (openrouter: {openrouter_model}) ---")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                print("(no OPENROUTER_API_KEY set)")
                return
            try:
                response = _call_openrouter(messages, openrouter_model, api_key)
            except Exception as e:
                print(f"(openrouter error: {e})")
                return
            print(response or "(empty response)")
        else:
            from cfmb.config import config
            from cfmb.llm_client import LLMClient
            print(f"--- LLM RESPONSE (ollama: {config.OLLAMA_MODEL}) ---")
            llm = LLMClient(config.OLLAMA_MODEL)
            response = asyncio.run(llm.get_completion(messages))
            print(response or "(empty response)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim-file", default=str(REPO_ROOT / "etc" / "sim_messages.json"))
    parser.add_argument("--with-llm", action="store_true")
    parser.add_argument("--openrouter", default=None, metavar="MODEL",
                        help="Use OpenRouter with this model id instead of local Ollama "
                             "(e.g. google/gemma-4-31b-it:free). Requires OPENROUTER_API_KEY.")
    parser.add_argument("--no-web", action="store_true",
                        help="Skip live meetup/handbook fetches (faster iteration).")
    parser.add_argument("--bot-user-id", default="999999999",
                        help="Discord user id of the bot (for role mapping and migration).")
    parser.add_argument("--meetup-url", default=DEFAULT_MEETUP_URL)
    parser.add_argument("--handbook-urls", default=",".join(DEFAULT_HANDBOOK_URLS),
                        help="Comma-separated wiki URLs to fetch and concatenate.")
    parser.add_argument("--discord-budget", type=int, default=100000)
    parser.add_argument("--chain-budget", type=int, default=10000)
    parser.add_argument("--handbook-budget", type=int, default=100000)
    parser.add_argument("--meetup-count", type=int, default=100)
    args = parser.parse_args()

    if not PROD_DB.exists():
        sys.exit(f"Expected prod sqlite copy at {PROD_DB}; aborting.")
    if not BASE_PROMPT_PATH.exists():
        sys.exit(f"Expected base prompt at {BASE_PROMPT_PATH}; aborting.")

    migrate_old_to_new(PROD_DB, TMP_DB, args.bot_user_id)
    db = DatabaseManager(str(TMP_DB))
    base_text = BASE_PROMPT_PATH.read_text()

    # Anchor "now" to the most recent migrated row so the 7-day window doesn't
    # clip out everything when the prod copy is older than today.
    with sqlite3.connect(str(TMP_DB)) as conn:
        row = conn.execute("SELECT MAX(timestamp) FROM messages").fetchone()
    anchor_now_iso = row[0] if row and row[0] else None
    if anchor_now_iso:
        print(f"Anchoring discord-content window at {anchor_now_iso}", file=sys.stderr)

    sim_file = Path(args.sim_file)
    if not sim_file.exists():
        sys.exit(f"sim file not found: {sim_file}")
    sims = json.loads(sim_file.read_text())
    handbook_urls = [u.strip() for u in args.handbook_urls.split(",") if u.strip()]

    for sim in sims:
        process_sim(
            db, sim,
            base_text=base_text,
            discord_budget=args.discord_budget,
            chain_budget=args.chain_budget,
            handbook_budget=args.handbook_budget,
            meetup_count=args.meetup_count,
            meetup_url=args.meetup_url,
            handbook_urls=handbook_urls,
            bot_user_id=args.bot_user_id,
            no_web=args.no_web,
            with_llm=args.with_llm,
            openrouter_model=args.openrouter,
            now_iso=anchor_now_iso,
        )
        print()


if __name__ == "__main__":
    main()
