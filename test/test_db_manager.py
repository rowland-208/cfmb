import os
import tempfile

import pytest

from cfmb.db_manager import DatabaseManager


@pytest.fixture
def db_manager():
    """Fixture to create a DatabaseManager instance with a temporary database file."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_db_file:
        db_name = temp_db_file.name
        manager = DatabaseManager(db_name)
        manager.initialize_db()
        yield manager
    os.remove(db_name)


def test_initialize_db(db_manager):
    """Test that initialize_db creates the necessary tables."""
    with db_manager._get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages';"
        )
        assert cursor.fetchone() is not None, "Table 'messages' should exist"

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system';"
        )
        assert cursor.fetchone() is not None, "Table 'system' should exist"

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='guild_points';"
        )
        assert cursor.fetchone() is not None, "Table 'guild_points' should exist"


def test_write_and_get_message(db_manager):
    """Test writing a message and retrieving recent messages."""
    server_id = "test_server"
    role = "user"
    content = "Hello, world!"

    db_manager.write_message(server_id, role, content)
    recent_messages = db_manager.get_recent_messages(server_id)

    assert len(recent_messages) == 1
    assert recent_messages[0]["role"] == role
    assert recent_messages[0]["content"] == content


def test_write_and_get_system_prompt(db_manager):
    """Test writing and retrieving a system prompt."""
    server_id = "test_server"
    content = "You are a helpful assistant."

    db_manager.write_system_prompt(server_id, content)
    system_prompt = db_manager.get_system_prompt(server_id)

    assert system_prompt["role"] == "system"
    assert system_prompt["content"] == content


def test_get_recent_messages_limit(db_manager):
    """Test retrieving recent messages with a limit."""
    server_id = "test_server"
    for i in range(5):
        db_manager.write_message(server_id, "user", f"Message {i}")

    recent_messages = db_manager.get_recent_messages(server_id, limit=3)
    assert len(recent_messages) == 3


def test_get_recent_messages_empty(db_manager):
    """Test retrieving recent messages when there are none."""
    server_id = "test_server"
    recent_messages = db_manager.get_recent_messages(server_id)
    assert len(recent_messages) == 0
    assert recent_messages == []


def test_get_system_prompt_default(db_manager):
    """Test getting system prompt when none is set, should return default."""
    server_id = "test_server_no_prompt"
    system_prompt = db_manager.get_system_prompt(server_id)
    assert system_prompt["role"] == "system"
    assert system_prompt["content"] == ""


def test_add_and_get_member_points(db_manager):
    """Test adding points to a member and retrieving their points."""
    member_id = 123
    initial_points = 10
    points_to_add = 5

    db_manager.add_member_points(member_id, initial_points)
    db_manager.add_member_points(member_id, points_to_add)  # Add more points

    total_points = db_manager.get_member_points(member_id)
    assert total_points == initial_points + points_to_add


def test_get_member_points_default(db_manager):
    """Test getting member points when member has no points, should return 0."""
    member_id = 456
    points = db_manager.get_member_points(member_id)
    assert points == 0


def test_get_recent_messages_order(db_manager):
    """Test that recent messages are returned in reverse chronological order."""
    server_id = "test_server_order"
    db_manager.write_message(server_id, "user", "Message 1")
    db_manager.write_message(server_id, "user", "Message 2")
    db_manager.write_message(server_id, "user", "Message 3")

    recent_messages = db_manager.get_recent_messages(server_id)
    assert recent_messages[0]["content"] == "Message 3"
    assert recent_messages[1]["content"] == "Message 2"
    assert recent_messages[2]["content"] == "Message 1"
