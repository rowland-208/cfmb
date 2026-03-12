from contextlib import contextmanager
import sqlite3
import struct

import sqlite_vec


class DatabaseManager:
    def __init__(self, db_name):
        self.db_name = db_name

    def initialize_db(self):
        """Creates the database and tables if they don't exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT,
                        chain_id TEXT,
                        message_id TEXT,
                        role TEXT,
                        content TEXT,
                        username TEXT,
                        channel_id TEXT,
                        channel_name TEXT,
                        user_id TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN username TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                try:
                    cursor.execute("ALTER TABLE messages RENAME COLUMN thread_id TO chain_id")
                except sqlite3.OperationalError:
                    pass  # already renamed or column doesn't exist
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN chain_id TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN message_id TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN channel_id TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN user_id TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN channel_name TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT,
                        content TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_points (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        member_id INTEGER,
                        points INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raw_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT,
                        message_id TEXT,
                        user_id TEXT,
                        username TEXT,
                        content TEXT,
                        channel_id TEXT,
                        channel_name TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                try:
                    cursor.execute("ALTER TABLE raw_messages ADD COLUMN channel_id TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                try:
                    cursor.execute("ALTER TABLE raw_messages ADD COLUMN channel_name TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT,
                        user_id TEXT,
                        username TEXT,
                        profile TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS summaries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        content TEXT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT,
                        message_id TEXT,
                        channel_id TEXT,
                        channel_name TEXT,
                        content TEXT,
                        embedding BLOB NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")

    def write_message(self, server_id, chain_id, role, content, username=None, message_id=None, channel_id=None, channel_name=None, user_id=None):
        """Writes a message to the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO messages (server_id, chain_id, message_id, role, content, username, channel_id, channel_name, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (server_id, chain_id, message_id, role, content, username, channel_id, channel_name, user_id),
                )
        except sqlite3.Error as e:
            print(f"Database write error: {e}")

    def write_system_prompt(self, server_id, content):
        """Writes a system prompt to the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO system (server_id, content) VALUES (?, ?)",
                    (server_id, content),
                )
        except sqlite3.Error as e:
            print(f"Database write error: {e}")

    def get_chain_id(self, message_id):
        """Returns the chain_id for a given Discord message_id, or None if not found."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT chain_id FROM messages WHERE message_id = ? LIMIT 1",
                    (message_id,),
                )
                row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return None

    def get_recent_chains(self, server_id, limit=3):
        """Returns the most recently active chain_ids for a server."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT chain_id FROM messages
                    WHERE server_id = ?
                    GROUP BY chain_id
                    ORDER BY MAX(timestamp) DESC LIMIT ?
                    """,
                    (server_id, limit),
                )
                rows = cursor.fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_recent_messages(self, server_id, chain_id, limit=10):
        """Retrieves recent messages from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role, content, username, channel_id, channel_name FROM messages
                    WHERE server_id = ? AND chain_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (server_id, chain_id, limit),
                )
                messages = cursor.fetchall()
            return [
                {"role": role, "content": content, "username": username, "channel_id": channel_id, "channel_name": channel_name}
                for role, content, username, channel_id, channel_name in reversed(messages)
            ]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_system_prompt(
        self, server_id
    ):  # Added server_id to system prompt retrieval for potential future server-specific prompts.
        """Retrieves the latest system prompt from the database for a server."""
        default = {"role": "system", "content": ""}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT content FROM system
                    WHERE server_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (server_id,),  # server_id as tuple for parameter substitution
                )
                prompt = cursor.fetchone()
            return {"role": "system", "content": prompt[0]} if prompt else default
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return default

    def write_raw_message(self, server_id, message_id, user_id, username, content, channel_id=None, channel_name=None):
        """Records every incoming message to the raw_messages table."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO raw_messages (server_id, message_id, user_id, username, content, channel_id, channel_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (server_id, message_id, user_id, username, content, channel_id, channel_name),
                )
        except sqlite3.Error as e:
            print(f"Database write error: {e}")

    def get_recent_raw_messages(self, server_id, limit=10):
        """Retrieves the most recent raw messages for a server."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT username, content, message_id, user_id, channel_id, channel_name FROM raw_messages
                    WHERE server_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (server_id, limit),
                )
                rows = cursor.fetchall()
            return [
                {"username": username, "content": content, "message_id": message_id, "user_id": user_id, "channel_id": channel_id, "channel_name": channel_name}
                for username, content, message_id, user_id, channel_id, channel_name in reversed(rows)
            ]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_raw_messages_24h(self, server_id):
        """Retrieves all raw messages from the past 24 hours, ordered by channel then time."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT username, content, channel_id, channel_name FROM raw_messages
                    WHERE server_id = ?
                      AND timestamp >= datetime('now', '-24 hours')
                      AND channel_name IS NOT NULL
                      AND content NOT LIKE '/%'
                    ORDER BY channel_id, timestamp ASC
                    """,
                    (server_id,),
                )
                rows = cursor.fetchall()
            return [
                {"username": username, "content": content, "channel_id": channel_id, "channel_name": channel_name}
                for username, content, channel_id, channel_name in rows
            ]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_raw_messages_date_range(self, server_id, start_iso, end_iso):
        """Retrieves raw messages between two ISO timestamps, ordered by channel then time."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT username, content, channel_id, channel_name FROM raw_messages
                    WHERE server_id = ?
                      AND timestamp >= ?
                      AND timestamp < ?
                      AND channel_name IS NOT NULL
                      AND content NOT LIKE '/%'
                    ORDER BY channel_id, timestamp ASC
                    """,
                    (server_id, start_iso, end_iso),
                )
                rows = cursor.fetchall()
            return [
                {"username": username, "content": content, "channel_id": channel_id, "channel_name": channel_name}
                for username, content, channel_id, channel_name in rows
            ]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_raw_messages_by_user_7d(self, server_id, user_id, limit=500):
        """Retrieves up to `limit` raw messages from a specific user in the past 7 days."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT username, content, channel_name FROM raw_messages
                    WHERE server_id = ?
                      AND user_id = ?
                      AND timestamp >= datetime('now', '-7 days')
                      AND content NOT LIKE '/%'
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (server_id, str(user_id), limit),
                )
                rows = cursor.fetchall()
            return [
                {"username": username, "content": content, "channel_name": channel_name}
                for username, content, channel_name in rows
            ]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_user_id_name_map(self, server_id):
        """Returns a dict of user_id -> most recent display name for active users in the past week."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT user_id, username FROM raw_messages
                    WHERE server_id = ?
                      AND timestamp >= datetime('now', '-7 days')
                      AND user_id IS NOT NULL
                    GROUP BY user_id
                    HAVING MAX(timestamp)
                    """,
                    (server_id,),
                ).fetchall()
            return {user_id: username for user_id, username in rows}
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return {}

    def get_previous_message_timestamp(self, server_id, user_id, current_message_id):
        """Returns the timestamp of the user's most recent message before the current one, within 7 days."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT timestamp FROM raw_messages
                    WHERE server_id = ? AND user_id = ? AND message_id != ?
                      AND timestamp >= datetime('now', '-7 days')
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (server_id, str(user_id), str(current_message_id)),
                ).fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return None

    def get_recent_raw_messages_by_user(self, server_id, user_id, limit=5):
        """Returns the most recent N messages from a specific user, excluding slash commands."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT content, channel_name FROM raw_messages
                    WHERE server_id = ? AND user_id = ? AND content NOT LIKE '/%'
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (server_id, str(user_id), limit),
                ).fetchall()
            return [{"content": content, "channel_name": channel_name} for content, channel_name in reversed(rows)]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_active_users_7d(self, server_id):
        """Returns distinct users who posted in the past 7 days, excluding slash commands."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT user_id, username FROM raw_messages
                    WHERE server_id = ?
                      AND timestamp >= datetime('now', '-7 days')
                      AND content NOT LIKE '/%'
                    """,
                    (server_id,),
                )
                rows = cursor.fetchall()
            return [{"user_id": user_id, "username": username} for user_id, username in rows]
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return []

    def get_latest_user_profile(self, server_id, user_id):
        """Returns the most recently saved profile for a user, or None if not found."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT profile, created_at FROM user_profiles
                    WHERE server_id = ? AND user_id = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (server_id, str(user_id)),
                ).fetchone()
            return {"profile": row[0], "created_at": row[1]} if row else None
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return None

    def write_user_profile(self, server_id, user_id, username, profile):
        """Inserts a generated user profile into the user_profiles table."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO user_profiles (server_id, user_id, username, profile) VALUES (?, ?, ?, ?)",
                    (server_id, str(user_id), username, profile),
                )
        except sqlite3.Error as e:
            print(f"Database write error: {e}")

    def write_rag_chunk(self, server_id: str, message_id: str, channel_id: str, channel_name: str, content: str, embedding: list[float]):
        """Stores a batched RAG chunk with its embedding."""
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO rag_chunks (server_id, message_id, channel_id, channel_name, content, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                    (server_id, message_id, channel_id, channel_name, content, blob),
                )
        except sqlite3.Error as e:
            print(f"RAG chunk write error: {e}")

    def get_latest_rag_chunk(self, channel_id: str) -> dict | None:
        """Returns the most recent rag_chunk for a channel, or None."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT id, message_id, channel_id, content FROM rag_chunks WHERE channel_id = ? ORDER BY id DESC LIMIT 1",
                    (channel_id,),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"RAG chunk read error: {e}")
            return None

    def update_rag_chunk(self, chunk_id: int, content: str, embedding: list[float]):
        """Updates content and embedding for an existing rag_chunk row."""
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE rag_chunks SET content = ?, embedding = ? WHERE id = ?",
                    (content, blob, chunk_id),
                )
        except sqlite3.Error as e:
            print(f"RAG chunk update error: {e}")

    def search_rag_chunks(self, server_id: str, embedding: list[float], limit: int = 5, hours: int | None = None, exclude_channels: set[str] | None = None) -> list[dict]:
        """Returns the closest RAG chunks to the given embedding vector, scoped to a server.
        Optionally restrict to chunks from the past `hours` hours and exclude specific channel IDs."""
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        time_filter = "AND timestamp >= datetime('now', ?)" if hours is not None else ""
        params = [blob, server_id] + ([f"-{hours} hours"] if hours is not None else [])
        if exclude_channels:
            placeholders = ",".join("?" * len(exclude_channels))
            channel_filter = f"AND channel_id NOT IN ({placeholders})"
            params.extend(exclude_channels)
        else:
            channel_filter = ""
        params.append(limit)
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT id, content, channel_id, channel_name, message_id,
                           vec_distance_cosine(embedding, ?) AS distance
                    FROM rag_chunks
                    WHERE server_id = ?
                    {time_filter}
                    {channel_filter}
                    ORDER BY distance ASC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
            return [
                {"id": chunk_id, "content": content, "channel_id": channel_id,
                 "channel_name": channel_name, "message_id": message_id, "distance": distance}
                for chunk_id, content, channel_id, channel_name, message_id, distance in rows
            ]
        except sqlite3.Error as e:
            print(f"RAG chunk search error: {e}")
            return []

    def write_summary(self, content):
        """Saves a generated daily summary to the summaries table."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO summaries (content) VALUES (?)",
                    (content,),
                )
        except sqlite3.Error as e:
            print(f"Summary write error: {e}")

    def get_recent_summaries(self, limit=3):
        """Returns the most recent summaries, newest first."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT timestamp, content FROM summaries ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [{"timestamp": row[0], "content": row[1]} for row in rows]
        except sqlite3.Error as e:
            print(f"Summary read error: {e}")
            return []

    def add_member_points(self, member_id, points):
        """Adds points to a member in the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                points = self.get_member_points(member_id) + points
                cursor.execute(
                    "INSERT INTO guild_points (member_id, points) VALUES (?, ?)",
                    (member_id, points),
                )
        except sqlite3.Error as e:
            print(f"Database write error: {e}")

    def get_member_points(self, member_id):
        """Retrieves points for a member from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT points FROM guild_points
                    WHERE member_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (member_id,),  # member.id as tuple for parameter substitution
                )
                points = cursor.fetchone()
            return points[0] if points else 0
        except sqlite3.Error as e:
            print(f"Database read error: {e}")
            return 0

    @contextmanager
    def _get_connection(self):
        """Internal method to get a database connection, now a context manager."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_name)
            conn.row_factory = sqlite3.Row
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
