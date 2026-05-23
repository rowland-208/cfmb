import sqlite3
from contextlib import contextmanager


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id    TEXT NOT NULL,
                    message_id   TEXT NOT NULL UNIQUE,
                    chain_id     TEXT,
                    user_id      TEXT NOT NULL,
                    username     TEXT,
                    channel_id   TEXT,
                    channel_name TEXT,
                    content      TEXT,
                    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chain ON messages (chain_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_server_time ON messages (server_id, timestamp)")

    def write_message(
        self, *,
        server_id: str,
        message_id: str,
        user_id: str,
        username: str | None,
        channel_id: str | None,
        channel_name: str | None,
        content: str,
        reply_to_message_id: str | None,
        is_mention: bool,
        bot_user_id: str,
        chain_id_override: str | None = None,
    ) -> str | None:
        """Resolves chain_id per the spec rules, writes the row, returns chain_id.

        Rules (first match wins):
        1. chain_id_override (explicit, used for bot replies).
        2. reply target has non-null chain_id -> inherit it.
        3. is_mention -> start a new chain (chain_id = message_id).
        4. else NULL.

        Duplicate message_id is silently ignored (UNIQUE constraint protects).
        """
        chain_id = self._resolve_chain_id(
            message_id=message_id,
            reply_to_message_id=reply_to_message_id,
            is_mention=is_mention,
            chain_id_override=chain_id_override,
        )
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO messages "
                    "(server_id, message_id, chain_id, user_id, username, "
                    " channel_id, channel_name, content) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (server_id, message_id, chain_id, user_id, username,
                     channel_id, channel_name, content),
                )
        except sqlite3.Error as e:
            print(f"DB write error: {e}")
        return chain_id

    def _resolve_chain_id(
        self, *,
        message_id: str,
        reply_to_message_id: str | None,
        is_mention: bool,
        chain_id_override: str | None,
    ) -> str | None:
        if chain_id_override is not None:
            return chain_id_override
        if reply_to_message_id is not None:
            parent_chain = self._lookup_chain_id(reply_to_message_id)
            if parent_chain is not None:
                return parent_chain
        if is_mention:
            return message_id
        return None

    def _lookup_chain_id(self, message_id: str) -> str | None:
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT chain_id FROM messages WHERE message_id = ?",
                    (message_id,),
                ).fetchone()
            return row["chain_id"] if row and row["chain_id"] is not None else None
        except sqlite3.Error as e:
            print(f"DB read error: {e}")
            return None

    def get_chain_messages(self, chain_id: str) -> list[dict]:
        """Returns chain rows oldest-first."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT message_id, user_id, username, channel_id, channel_name, "
                    "content, timestamp FROM messages "
                    "WHERE chain_id = ? ORDER BY timestamp ASC, id ASC",
                    (chain_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            print(f"DB read error: {e}")
            return []

    def get_recent_discord_messages(
        self,
        server_id: str,
        current_chain_id: str | None,
        excluded_channel_ids: list[str],
        days: int = 7,
    ) -> list[dict]:
        """Returns candidate rows for the system-prompt discord section.

        Filters: server_id match, channel_id NOT IN excluded, chain_id IS DISTINCT
        FROM current_chain_id (so the current chain's rows are excluded but rows from
        other chains AND chain-less rows are kept), within the past `days` days.
        Ordered newest-first. Caller applies the token cap.
        """
        params: list = [server_id, f"-{int(days)} days"]
        clauses = [
            "server_id = ?",
            "timestamp >= datetime('now', ?)",
        ]
        if current_chain_id is not None:
            clauses.append("(chain_id IS NULL OR chain_id != ?)")
            params.append(current_chain_id)
        if excluded_channel_ids:
            placeholders = ",".join("?" * len(excluded_channel_ids))
            clauses.append(f"(channel_id IS NULL OR channel_id NOT IN ({placeholders}))")
            params.extend(excluded_channel_ids)
        sql = (
            "SELECT message_id, user_id, username, channel_id, channel_name, "
            "content, timestamp FROM messages WHERE "
            + " AND ".join(clauses)
            + " ORDER BY timestamp DESC"
        )
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            print(f"DB read error: {e}")
            return []

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()
