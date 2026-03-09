import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY
import pytest

import cfmb.bot as bot  # Import the module containing your bot's code
from cfmb.config import Config


@pytest.fixture
def mock_config():
    mock_config = MagicMock(spec=Config)
    mock_config.NUM_CLOSEST_MESSAGES = 10
    mock_config.DISCORD_MAX_MESSAGE_LENGTH = 2000
    mock_config.ADMIN1_USER_ID = 123
    mock_config.ADMIN2_USER_ID = 456
    mock_config.BOT_USER_ID = 789
    return mock_config


@pytest.fixture
def mock_db_manager():
    mock = MagicMock()
    mock.initialize_db = MagicMock()  # No return value needed, it's called in on_ready
    mock.get_chain_id.return_value = None
    mock.get_recent_chains.return_value = ["99999"]
    mock.get_recent_messages.return_value = [
        {"role": "user", "content": "Message 1", "username": None},
        {"role": "assistant", "content": "Message 2", "username": None},
    ]
    mock.get_system_prompt.return_value = {"role": "system", "content": "System prompt"}
    mock.write_message = MagicMock()  # No return value checks
    mock.write_system_prompt = MagicMock()  # No return value checks
    mock.add_member_points = MagicMock()
    mock.get_member_points.return_value = 0
    return mock


@pytest.fixture
def mock_llm_client():
    mock = MagicMock()
    mock.get_completion = AsyncMock(return_value="LLM response")
    return mock


@pytest.fixture
def mock_discord_message():
    mock_message = AsyncMock()
    mock_message.author.id = 999  # Default author ID
    mock_message.author.display_name = "Test User"
    mock_message.guild.id = 12345
    mock_message.channel.id = 99999
    mock_message.content = ""  # Default content
    mock_message.mentions = []  # No mentions default.
    mock_message.channel.send = AsyncMock()  # For assertions on send.
    mock_message.channel.typing = MagicMock(return_value=AsyncMock())
    mock_message.add_reaction = AsyncMock()
    mock_message.attachments = []
    return mock_message


@pytest.fixture
def mock_client(mock_db_manager, mock_llm_client):
    # This is more complex due to the bot structure.  We use a simple mock object here.
    mock_client = MagicMock()
    mock_client.user.id = bot.config.BOT_USER_ID
    mock_client.user.name = "TestBot"
    return mock_client


@pytest.mark.asyncio
async def test_on_ready(mock_db_manager, mock_client):
    bot.db_manager = mock_db_manager  # Inject
    bot.client = mock_client
    await bot.on_ready()
    mock_db_manager.initialize_db.assert_called_once()


@pytest.mark.asyncio
async def test_on_message_self_message(mock_discord_message, mock_client):
    bot.client = mock_client
    mock_discord_message.author = mock_client.user  # Message from the bot itself.
    await bot.on_message(mock_discord_message)
    mock_discord_message.channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_dm(mock_discord_message, mock_client):
    bot.client = mock_client
    mock_discord_message.guild = None  # Simulate a DM.
    await bot.on_message(mock_discord_message)
    mock_discord_message.channel.send.assert_called_once_with(
        "I can only respond to messages in servers."
    )


@pytest.mark.asyncio
async def test_on_message_nvda_reaction(mock_discord_message, mock_client):
    bot.client = mock_client
    mock_discord_message.content = "NVDA"  # Case-sensitive check.
    await bot.on_message(mock_discord_message)
    mock_discord_message.add_reaction.assert_called_once_with("👀")


@pytest.mark.asyncio
async def test_on_message_nvda_no_reaction(mock_discord_message, mock_client):
    bot.client = mock_client
    mock_discord_message.content = "nvda"  # Case-sensitive check.
    await bot.on_message(mock_discord_message)
    mock_discord_message.add_reaction.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_no_command(mock_discord_message, mock_client):
    bot.client = mock_client
    mock_discord_message.content = "Just some text"
    await bot.on_message(mock_discord_message)
    # Assert that none of the command handlers were called
    mock_discord_message.channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_handle_system_command(
    mock_discord_message, mock_db_manager, mock_config
):
    bot.db_manager = mock_db_manager
    bot.config = mock_config
    mock_discord_message.content = "!system"
    await bot.handle_system_command(mock_discord_message, "12345")
    mock_db_manager.get_system_prompt.assert_called_once_with("12345")
    mock_discord_message.channel.send.assert_called_once_with(
        "System: System prompt"
    )  # Check the constructed string


@pytest.mark.asyncio
async def test_handle_set_system_command(
    mock_discord_message, mock_db_manager, mock_config
):
    bot.db_manager = mock_db_manager
    bot.config = mock_config
    mock_discord_message.content = "/set_system New system prompt"
    await bot.handle_set_system_command(mock_discord_message, "12345")
    mock_db_manager.write_system_prompt.assert_called_once_with(
        "12345", "New system prompt"
    )
    mock_discord_message.channel.send.assert_called_once_with("System prompt set")


@pytest.mark.asyncio
async def test_handle_exec_command_authorized(mock_discord_message, mock_config):
    bot.config = mock_config
    mock_discord_message.author.id = mock_config.ADMIN2_USER_ID
    mock_discord_message.content = "/exec echo test"
    with patch("subprocess.check_output", return_value=b"test\n") as mock_subprocess:
        await bot.handle_exec_command(mock_discord_message)
        mock_subprocess.assert_called_once_with("echo test", shell=True)
        print(mock_discord_message.channel.send.call_args)
        mock_discord_message.channel.send.assert_called_once_with("```test\n```")


@pytest.mark.asyncio
async def test_handle_exec_command_unauthorized(mock_discord_message, mock_config):
    bot.config = mock_config
    mock_discord_message.author.id = 999
    mock_discord_message.content = "!exec echo test"
    await bot.handle_exec_command(mock_discord_message)
    mock_discord_message.channel.send.assert_called_once_with(
        "You do not have permission to execute commands ❌"
    )


@pytest.mark.asyncio
async def test_handle_exec_command_exception(mock_discord_message, mock_config):
    bot.config = mock_config
    mock_discord_message.author.id = mock_config.ADMIN2_USER_ID
    mock_discord_message.content = "!exec bad_command"
    with patch(
        "subprocess.check_output", side_effect=Exception("Error")
    ) as mock_subprocess:
        await bot.handle_exec_command(mock_discord_message)

        mock_discord_message.channel.send.assert_called_once()
        sent_message = mock_discord_message.channel.send.call_args[0][
            0
        ]  # Access the sent message
        assert sent_message.startswith("```Error")
        assert sent_message.endswith("```")


@pytest.mark.asyncio
async def test_handle_help_command(mock_discord_message):
    await bot.handle_help_command(mock_discord_message)
    mock_discord_message.channel.send.assert_called_once()  # Check that a message was sent
    sent_message = mock_discord_message.channel.send.call_args[0][0]
    assert "/system" in sent_message
    assert "/points" in sent_message


def test_resolve_chain_id_no_reference(mock_discord_message, mock_db_manager):
    """A message with no reference starts a new chain using its own id."""
    bot.db_manager = mock_db_manager
    mock_discord_message.reference = None
    mock_discord_message.id = 111
    assert bot.resolve_chain_id(mock_discord_message) == "111"


def test_resolve_chain_id_reference_found(mock_discord_message, mock_db_manager):
    """A reply whose parent is in the DB inherits the parent's chain_id."""
    bot.db_manager = mock_db_manager
    mock_discord_message.reference = MagicMock()
    mock_discord_message.reference.message_id = 999
    mock_db_manager.get_chain_id.return_value = "chain_abc"
    assert bot.resolve_chain_id(mock_discord_message) == "chain_abc"


def test_resolve_chain_id_reference_not_found(mock_discord_message, mock_db_manager):
    """A reply whose parent is not in the DB uses the parent message_id as chain_id."""
    bot.db_manager = mock_db_manager
    mock_discord_message.reference = MagicMock()
    mock_discord_message.reference.message_id = 999
    mock_db_manager.get_chain_id.return_value = None
    assert bot.resolve_chain_id(mock_discord_message) == "999"


@pytest.mark.asyncio
async def test_handle_guild_points_command_get(
    mock_discord_message, mock_db_manager, mock_config
):
    bot.db_manager = mock_db_manager
    bot.config = mock_config
    # Test getting points.
    mock_discord_message.author.id = 1
    mock_discord_message.author.display_name = "User1"
    mock_db_manager.get_member_points.return_value = 10
    mock_discord_message.content = "/points"

    await bot.handle_guild_points_command(mock_discord_message)
    mock_db_manager.get_member_points.assert_called_with(1)
    mock_discord_message.channel.send.assert_called_with(
        "🏆 Guild Points 🏆\nUser1 --> 10"
    )
