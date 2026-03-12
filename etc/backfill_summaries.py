#!/usr/bin/env python3
"""
Backfill the summaries table with one summary per day for the past 7 days.

Usage (from repo root):
    source ~/.cfmb && .venv/bin/python etc/backfill_summaries.py
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from cfmb.config import config
from cfmb.db_manager import DatabaseManager
from cfmb.llm_client import LLMClient


SUMMARY_SYSTEM_PROMPT = (
    "You are an analyst for the Cape Fear Makers Guild Discord server. "
    "You will be given a transcript of messages grouped by channel. "
    "Identify the five most important facts, events, announcements, plans, or pieces of information. "
    "For each fact, list the users involved and the channel it came from.\n\n"
    "Return ONLY the facts in this exact format, separated by ---:\n\n"
    "what: one sentence describing the fact\n"
    "users: user1, user2\n"
    "channel: #channel-name\n"
    "---\n"
    "what: another fact\n"
    "users: user3\n"
    "channel: #other-channel\n\n"
    "Do not add any other text, headers, or commentary."
)


async def main():
    db = DatabaseManager(config.DB_NAME)
    db.initialize_db()
    llm = LLMClient(config.OLLAMA_MODEL)

    with db._get_connection() as conn:
        server_ids = [
            row[0]
            for row in conn.execute("SELECT DISTINCT server_id FROM raw_messages").fetchall()
        ]

    if not server_ids:
        print("No messages found in the database.")
        return

    excluded = set(config.DEV_EXCLUDED_CHANNELS.split(",")) if config.DEV_EXCLUDED_CHANNELS else set()
    now = datetime.now(timezone.utc)

    for server_id in server_ids:
        print(f"Server {server_id}:")
        for days_ago in range(7, 0, -1):
            day_start = (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            label = day_start.strftime("%Y-%m-%d")

            raw = db.get_raw_messages_date_range(server_id, day_start.isoformat(), day_end.isoformat())
            if not raw:
                print(f"  {label}: no messages, skipping.")
                continue

            channels = {}
            for m in raw:
                cid = m["channel_id"] or "unknown"
                if cid in excluded:
                    continue
                channels.setdefault(cid, {"name": m["channel_name"] or cid, "messages": []})
                channels[cid]["messages"].append(m)

            if not channels:
                print(f"  {label}: no messages after exclusions, skipping.")
                continue

            transcript_blocks = []
            for data in channels.values():
                ch_name = data["name"]
                lines = [f"{m['username']}: {m['content']}" for m in data["messages"]]
                transcript_blocks.append(f"#{ch_name}\n" + "\n".join(lines))

            transcript = "\n---\n".join(transcript_blocks)

            prompt = [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ]

            print(f"  {label}: generating summary...", end=" ", flush=True)
            result = await llm.get_completion(prompt)
            if result:
                with db._get_connection() as conn:
                    conn.execute(
                        "INSERT INTO summaries (timestamp, content) VALUES (?, ?)",
                        (day_end.isoformat(), result),
                    )
                print("saved.")
            else:
                print("LLM returned nothing, skipping.")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
