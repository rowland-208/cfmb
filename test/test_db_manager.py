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
    chain_id = "test_chain"
    role = "user"
    content = "Hello, world!"

    db_manager.write_message(server_id, chain_id, role, content)
    recent_messages = db_manager.get_recent_messages(server_id, chain_id)

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
    chain_id = "test_chain"
    for i in range(5):
        db_manager.write_message(server_id, chain_id, "user", f"Message {i}")

    recent_messages = db_manager.get_recent_messages(server_id, chain_id, limit=3)
    assert len(recent_messages) == 3


def test_get_recent_messages_empty(db_manager):
    """Test retrieving recent messages when there are none."""
    server_id = "test_server"
    chain_id = "test_chain"
    recent_messages = db_manager.get_recent_messages(server_id, chain_id)
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
    """Test that recent messages are returned in chronological order."""
    server_id = "test_server_order"
    chain_id = "test_chain"
    db_manager.write_message(server_id, chain_id, "user", "Message 1")
    db_manager.write_message(server_id, chain_id, "user", "Message 2")
    db_manager.write_message(server_id, chain_id, "user", "Message 3")

    recent_messages = db_manager.get_recent_messages(server_id, chain_id)
    assert recent_messages[0]["content"] == "Message 3"
    assert recent_messages[1]["content"] == "Message 2"
    assert recent_messages[2]["content"] == "Message 1"


def test_get_recent_messages_chain_isolation(db_manager):
    """Test that messages from different chains are isolated."""
    server_id = "test_server"
    db_manager.write_message(server_id, "chain_a", "user", "Chain A message")
    db_manager.write_message(server_id, "chain_b", "user", "Chain B message")

    messages_a = db_manager.get_recent_messages(server_id, "chain_a")
    messages_b = db_manager.get_recent_messages(server_id, "chain_b")

    assert len(messages_a) == 1
    assert messages_a[0]["content"] == "Chain A message"
    assert len(messages_b) == 1
    assert messages_b[0]["content"] == "Chain B message"


def test_get_chain_id(db_manager):
    """Test looking up a chain_id by Discord message_id."""
    db_manager.write_message("server", "chain_abc", "user", "Hello", message_id="msg_111")

    assert db_manager.get_chain_id("msg_111") == "chain_abc"
    assert db_manager.get_chain_id("msg_999") is None


def test_get_recent_chains(db_manager):
    """Test retrieving the most recently active chains for a server."""
    server_id = "test_server"
    db_manager.write_message(server_id, "chain_1", "user", "First")
    db_manager.write_message(server_id, "chain_2", "user", "Second")
    db_manager.write_message(server_id, "chain_3", "user", "Third")
    db_manager.write_message(server_id, "chain_4", "user", "Fourth")

    chains = db_manager.get_recent_chains(server_id, limit=3)
    assert len(chains) == 3
    assert "chain_4" in chains
    assert "chain_3" in chains
    assert "chain_2" in chains
    assert "chain_1" not in chains
