#!/usr/bin/env python3
"""Migrate an old-schema cfmb_db.sqlite into the new collapsed schema.

The new bot's `messages` table replaces the prior `messages` + `raw_messages`
split. This script copies:
  - Every row from old `raw_messages` (one-to-one to new `messages`)
  - The `chain_id` for any old `messages.message_id` that overlaps
  - Old assistant rows from `messages` (role='assistant') as bot replies,
    stamped with the supplied --bot-user-id and inheriting their chain_id

Other old tables (system, user_profiles, summaries, rag_chunks,
message_embeddings, guild_points) are dropped — those features are gone in the
context-bot redesign.

Usage:
    python etc/migrate.py --src cfmb_db.sqlite --dst cfmb.sqlite --bot-user-id <id>

Refuses to overwrite an existing destination unless --force is passed.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cfmb.db_manager import DatabaseManager


def migrate(src: Path, dst: Path, bot_user_id: str) -> tuple[int, int]:
    new = DatabaseManager(str(dst))
    new.initialize_db()

    source = sqlite3.connect(src)
    source.row_factory = sqlite3.Row

    chains: dict[str, str] = {}
    for row in source.execute(
        "SELECT message_id, chain_id FROM messages "
        "WHERE chain_id IS NOT NULL AND message_id IS NOT NULL"
    ):
        chains[row["message_id"]] = row["chain_id"]

    raw_rows = source.execute(
        "SELECT server_id, message_id, user_id, username, channel_id, channel_name, "
        "content, timestamp FROM raw_messages WHERE message_id IS NOT NULL ORDER BY id ASC"
    ).fetchall()

    bot_rows = source.execute(
        "SELECT chain_id, message_id, content, channel_id, channel_name, timestamp "
        "FROM messages WHERE role='assistant' AND message_id IS NOT NULL"
    ).fetchall()

    source.close()

    destination = sqlite3.connect(str(dst))
    raw_inserted = 0
    for r in raw_rows:
        cur = destination.execute(
            "INSERT OR IGNORE INTO messages (server_id, message_id, chain_id, user_id, "
            "username, channel_id, channel_name, content, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["server_id"], r["message_id"], chains.get(r["message_id"]),
             r["user_id"] or "unknown", r["username"], r["channel_id"],
             r["channel_name"], r["content"] or "", r["timestamp"]),
        )
        raw_inserted += cur.rowcount

    bot_inserted = 0
    for r in bot_rows:
        srv_row = destination.execute(
            "SELECT server_id FROM messages WHERE chain_id = ? LIMIT 1",
            (r["chain_id"],),
        ).fetchone()
        server_id = srv_row[0] if srv_row else "unknown"
        cur = destination.execute(
            "INSERT OR IGNORE INTO messages (server_id, message_id, chain_id, user_id, "
            "username, channel_id, channel_name, content, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (server_id, r["message_id"], r["chain_id"], bot_user_id, "bot",
             r["channel_id"], r["channel_name"], r["content"] or "", r["timestamp"]),
        )
        bot_inserted += cur.rowcount
    destination.commit()
    destination.close()
    return raw_inserted, bot_inserted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path,
                        help="Path to old-schema cfmb_db.sqlite")
    parser.add_argument("--dst", required=True, type=Path,
                        help="Path to write the new-schema sqlite (will not overwrite without --force)")
    parser.add_argument("--bot-user-id", required=True,
                        help="Discord user id of the bot (assigned to migrated assistant rows)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite destination if it exists")
    args = parser.parse_args()

    if not args.src.exists():
        sys.exit(f"Source DB not found: {args.src}")
    if args.dst.exists():
        if not args.force:
            sys.exit(f"Destination exists: {args.dst}. Pass --force to overwrite.")
        args.dst.unlink()

    raw, bot = migrate(args.src, args.dst, args.bot_user_id)
    print(f"Wrote {raw} raw rows and {bot} bot rows to {args.dst}")


if __name__ == "__main__":
    main()
