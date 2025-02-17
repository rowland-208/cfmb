from contextlib import contextmanager
import sqlite3


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
                        role TEXT,
                        content TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
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
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")

    def write_message(self, server_id, role, content):
        """Writes a message to the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO messages (server_id, role, content) VALUES (?, ?, ?)",
                    (server_id, role, content),
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

    def get_recent_messages(self, server_id, limit=10):
        """Retrieves recent messages from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role, content FROM messages
                    WHERE server_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (server_id, limit),
                )
                messages = cursor.fetchall()
            return [
                {"role": role, "content": content}
                for role, content in reversed(messages)
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
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
