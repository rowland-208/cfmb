#!/usr/bin/env python3
"""
Backfill rag_chunks from the past 24 hours of raw_messages.

Usage (from repo root):
    source ~/.cfmb && .venv/bin/python etc/backfill_rag_chunks.py
"""
import asyncio
import sys

from tqdm import tqdm

sys.path.insert(0, ".")
from cfmb.config import config
from cfmb.db_manager import DatabaseManager
from cfmb.llm_client import LLMClient

BATCH_THRESHOLD = 512
BATCH_MAX_CONTENT = 2048


async def main():
    if not config.OLLAMA_EMBEDDING_MODEL:
        print("OLLAMA_EMBEDDING_MODEL is not set — nothing to do.")
        return

    db = DatabaseManager(config.DB_NAME)
    db.initialize_db()
    llm = LLMClient(config.OLLAMA_MODEL)

    with db._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT server_id, message_id, username, content, channel_id, channel_name
            FROM raw_messages
            WHERE timestamp >= datetime('now', '-7 days')
              AND content IS NOT NULL
              AND trim(content) != ''
              AND content NOT LIKE '/%'
              AND channel_name IS NOT NULL
            ORDER BY channel_id, timestamp ASC
            """
        ).fetchall()

    if not rows:
        print("No messages from the past 24 hours.")
        return

    print(f"Processing {len(rows)} messages into RAG chunks with {config.OLLAMA_EMBEDDING_MODEL}...")

    # Group by channel, batch into chunks
    chunks_created = 0
    chunks_updated = 0
    failed = 0

    with tqdm(rows, unit="msg") as bar:
        for row in bar:
            server_id = row["server_id"]
            message_id = row["message_id"]
            username = row["username"]
            content = row["content"]
            channel_id = row["channel_id"]
            channel_name = row["channel_name"]

            formatted = f"{username}: {content}"
            latest = db.get_latest_rag_chunk(channel_id)

            if latest and len(latest["content"]) <= BATCH_THRESHOLD:
                new_content = (latest["content"] + "\n" + formatted)[:BATCH_MAX_CONTENT]
                embedding = await llm.get_embedding(new_content, config.OLLAMA_EMBEDDING_MODEL)
                if embedding:
                    db.update_rag_chunk(latest["id"], new_content, embedding)
                    chunks_updated += 1
                else:
                    failed += 1
                    bar.write(f"  failed embedding update for {message_id}")
            else:
                new_content = formatted[:BATCH_MAX_CONTENT]
                embedding = await llm.get_embedding(new_content, config.OLLAMA_EMBEDDING_MODEL)
                if embedding:
                    db.write_rag_chunk(server_id, message_id, channel_id, channel_name, new_content, embedding)
                    chunks_created += 1
                else:
                    failed += 1
                    bar.write(f"  failed embedding new chunk for {message_id}")

    print(f"\nDone. {chunks_created} chunks created, {chunks_updated} updates, {failed} failed.")


if __name__ == "__main__":
    asyncio.run(main())
