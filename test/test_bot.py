import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY
import pytest

import cfmb.bot as bot  # Import the module containing your bot's code
from cfmb.config import Config


@pytest.fixture
def mock_config():
    mock_config = MagicMock(spec=Config)
    mock_config.CONTEXT_SIZE = 10
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
async def test_handle_context_command(
    mock_discord_message, mock_db_manager, mock_config
):
    bot.db_manager = mock_db_manager
    bot.config = mock_config
    mock_discord_message.content = "!context"

    await bot.handle_context_command(mock_discord_message, "12345", "99999")
    mock_db_manager.get_recent_chains.assert_called_once_with("12345", limit=4)
    mock_db_manager.get_recent_messages.assert_called_once_with("12345", "99999", limit=6)

    expected_context_str = "--- Chain 99999 (current) ---\n  user: Message 1\n  assistant: Message 2"
    mock_discord_message.channel.send.assert_called_once_with(expected_context_str)


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
    mock_discord_message.content = "!set_system New system prompt"
    await bot.handle_set_system_command(mock_discord_message, "12345")
    mock_db_manager.write_system_prompt.assert_called_once_with(
        "12345", "New system prompt"
    )
    mock_discord_message.channel.send.assert_called_once_with("System prompt set")


@pytest.mark.asyncio
async def test_handle_exec_command_authorized(mock_discord_message, mock_config):
    bot.config = mock_config
    mock_discord_message.author.id = mock_config.ADMIN2_USER_ID
    mock_discord_message.content = "!exec echo test"
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
    assert "!system" in sent_message
    assert "!points" in sent_message


@pytest.mark.asyncio
async def test_handle_event_command(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.db_manager = mock_db_manager
    bot.llm_client = mock_llm_client
    # Mock bot mention handler
    with patch(
        "cfmb.bot.handle_bot_mention", new_callable=AsyncMock
    ) as mock_handle_bot_mention:
        mock_discord_message.content = "!events What are the next events?"
        await bot.handle_event_command(mock_discord_message, "12345", "99999")

        # Check if handle_bot_mention was called correctly
        mock_handle_bot_mention.assert_called_once()
        # Correct the assertion to check for the modified message content
        assert (
            mock_handle_bot_mention.call_args[0][0].content
            == "Tell me about events at https://www.meetup.com/cape-fear-makers-guild-meetup-group/  What are the next events?"
        )
        assert mock_handle_bot_mention.call_args[0][1] == "12345"
        assert mock_handle_bot_mention.call_args[0][2] == "99999"


@pytest.mark.asyncio
async def test_handle_bot_mention_enqueues(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.llm_queue = asyncio.Queue()

    mock_discord_message.content = f"<@{mock_config.BOT_USER_ID}> Hello"
    await bot.handle_bot_mention(mock_discord_message, "12345", "99999")

    assert bot.llm_queue.qsize() == 1
    queued_message, queued_server_id, queued_chain_id = bot.llm_queue.get_nowait()
    assert queued_message == mock_discord_message
    assert queued_server_id == "12345"
    assert queued_chain_id == "99999"


@pytest.mark.asyncio
async def test_process_llm_request(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.db_manager = mock_db_manager
    bot.llm_client = mock_llm_client

    mock_discord_message.content = f"<@{mock_config.BOT_USER_ID}> Hello"
    with patch(
        "cfmb.bot.get_webpage_text", return_value="Webpage text"
    ) as mock_get_webpage:
        with patch(
            "cfmb.bot.extract_first_url", return_value="http://example.com"
        ) as mock_extract:

            await bot.process_llm_request(mock_discord_message, "12345", "99999")

            mock_db_manager.write_message.assert_has_calls(
                [
                    call("12345", "99999", "user", "<@Maker bot> Hello", username="Test User", message_id=ANY),
                    call("12345", "99999", "assistant", "LLM response", message_id=ANY),
                ]
            )
            mock_db_manager.get_recent_messages.assert_called_with(
                "12345", "99999", mock_config.CONTEXT_SIZE
            )
            mock_db_manager.get_system_prompt.assert_called_once()
            mock_extract.assert_called_once_with("<@Maker bot> Hello")
            mock_get_webpage.assert_called_once_with("http://example.com")
            mock_llm_client.get_completion.assert_called()  # Check args more closely in sep. test
            mock_discord_message.reply.assert_called_once_with("LLM response")


@pytest.mark.asyncio
async def test_process_llm_request_no_url(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.db_manager = mock_db_manager
    bot.llm_client = mock_llm_client
    mock_discord_message.content = f"<@{mock_config.BOT_USER_ID}> Hello"
    with patch("cfmb.bot.get_webpage_text") as mock_get_webpage:
        with patch("cfmb.bot.extract_first_url", return_value=None) as mock_extract:
            await bot.process_llm_request(mock_discord_message, "12345", "99999")
            print(mock_extract.call_args)
            mock_extract.assert_called_once_with("<@Maker bot> Hello")
            mock_get_webpage.assert_not_called()


@pytest.mark.asyncio
async def test_process_llm_request_llm_error(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.db_manager = mock_db_manager
    bot.llm_client = mock_llm_client
    mock_llm_client.get_completion.return_value = None  # Simulate an error
    mock_discord_message.content = f"<@{mock_config.BOT_USER_ID}> Hello"

    await bot.process_llm_request(mock_discord_message, "12345", "99999")

    mock_discord_message.reply.assert_called_once_with(
        "Sorry, I encountered an error generating a response."
    )
    mock_db_manager.write_message.assert_called_once_with(
        "12345", "99999", "user", "<@Maker bot> Hello", username="Test User", message_id=ANY
    )

    calls = mock_db_manager.write_message.call_args_list
    expected_not_called = call("12345", "assistant", "LLM response")
    if calls:
        assert not any(
            expected_not_called == c for c in calls
        ), f"write_message should not have been called with {expected_not_called}"
    else:
        pass


@pytest.mark.asyncio
async def test_process_llm_request_llm_call_args(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.db_manager = mock_db_manager
    bot.llm_client = mock_llm_client
    mock_db_manager.get_recent_messages.return_value = [
        {"role": "user", "content": "User message"}
    ]
    mock_db_manager.get_system_prompt.return_value = {
        "role": "system",
        "content": "System prompt",
    }

    with patch(
        "cfmb.bot.get_webpage_text", return_value="Webpage text"
    ) as mock_get_webpage:
        with patch(
            "cfmb.bot.extract_first_url", return_value="http://example.com"
        ) as mock_extract:
            mock_discord_message.content = (
                f"<@{mock_config.BOT_USER_ID}> Hello http://example.com"
            )
            await bot.process_llm_request(mock_discord_message, "12345", "99999")
            expected_messages = [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "User message"},
                {"role": "tool", "content": "Webpage text"},
            ]

            mock_llm_client.get_completion.assert_called_once_with(expected_messages)


@pytest.mark.asyncio
async def test_process_llm_request_with_image_attachments(
    mock_discord_message, mock_db_manager, mock_llm_client, mock_config
):
    bot.config = mock_config
    bot.db_manager = mock_db_manager
    bot.llm_client = mock_llm_client
    mock_db_manager.get_recent_messages.return_value = [
        {"role": "user", "content": "User message"}
    ]
    mock_db_manager.get_system_prompt.return_value = {
        "role": "system",
        "content": "System prompt",
    }

    image_data = b"fake-image-bytes"
    mock_attachment = AsyncMock()
    mock_attachment.content_type = "image/png"
    mock_attachment.read.return_value = image_data
    mock_discord_message.attachments = [mock_attachment]

    mock_discord_message.content = f"<@{mock_config.BOT_USER_ID}> Describe this image"
    with patch("cfmb.bot.extract_first_url", return_value=None):
        await bot.process_llm_request(mock_discord_message, "12345", "99999")

        expected_messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User message", "images": [image_data]},
        ]
        mock_llm_client.get_completion.assert_called_once_with(expected_messages)


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
    mock_discord_message.content = "!points"

    await bot.handle_guild_points_command(mock_discord_message)
    mock_db_manager.get_member_points.assert_called_with(1)
    mock_discord_message.channel.send.assert_called_with(
        "🏆 Guild Points 🏆\nUser1 --> 10"
    )
