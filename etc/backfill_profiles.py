#!/usr/bin/env python3
"""
Generate and persist user profiles for all active users from the past week.

Usage (from repo root):
    source ~/.cfmb && .venv/bin/python etc/generate_profiles.py
"""
import asyncio
import sys

sys.path.insert(0, ".")
from cfmb.bot import _build_profile_prompt, _resolve_mentions
from cfmb.config import config
from cfmb.db_manager import DatabaseManager
from cfmb.llm_client import LLMClient


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

    with db._get_connection() as conn:
        deleted = conn.execute("DELETE FROM user_profiles").rowcount
    print(f"Deleted {deleted} existing profiles.")

    for server_id in server_ids:
        users = db.get_active_users_7d(server_id)
        print(f"Server {server_id}: {len(users)} active users in the past week.")

        id_to_name = db.get_user_id_name_map(server_id)
        id_to_name[str(config.BOT_USER_ID)] = "Maker bot"

        for user in users:
            user_id = user["user_id"]
            username = user["username"]
            raw = db.get_raw_messages_by_user_7d(server_id, user_id)
            if len(raw) < 20:
                print(f"  {username}: fewer than 20 messages, skipping.")
                continue

            transcript = "\n".join(
                f"[{m['channel_name'] or 'unknown'}] {_resolve_mentions(m['content'], id_to_name)}"
                for m in raw
                if m["content"].strip()
            )

            print(f"  {username}: generating profile from {len(raw)} messages...", end=" ", flush=True)
            prompt = _build_profile_prompt(username, transcript)
            profile = await llm.get_completion(prompt)
            if profile:
                db.write_user_profile(server_id, user_id, username, profile)
                print("saved.")
            else:
                print("LLM returned nothing, skipping.")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
