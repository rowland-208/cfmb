import re
import subprocess

import discord

from cfmb.config import config
from cfmb.db_manager import DatabaseManager
from cfmb.llm_client import LLMClient
from cfmb.webfetch import get_webpage_text, extract_first_url


intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
db_manager = DatabaseManager(config.DB_NAME)
llm_client = LLMClient(config.OLLAMA_MODEL)


@client.event
async def on_ready():
    db_manager.initialize_db()
    print(f"Bot is online as {client.user}!")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.guild is None:
        await message.channel.send("I can only respond to messages in servers.")
        return

    server_id = str(message.guild.id)

    if "NVDA" in message.content:
        await message.add_reaction("👀")

    if message.content.startswith("!context"):
        await handle_context_command(message, server_id)
        return

    if message.content.startswith("!events"):
        await handle_event_command(message, server_id)
        return

    if message.content.startswith("!help"):
        await handle_help_command(message)
        return

    if message.content.startswith("!points"):
        await handle_guild_points_command(message)
        return

    if message.content.startswith("!system"):
        await handle_system_command(message, server_id)
        return

    if message.content.startswith("!set_system"):
        await handle_set_system_command(message, server_id)
        return

    if message.content.startswith("!exec"):
        await handle_exec_command(message)
        return

    if client.user in message.mentions:
        await handle_bot_mention(message, server_id)
        return


async def handle_guild_points_command(message):
    valid_user_ids = (config.ADMIN1_USER_ID, config.ADMIN2_USER_ID)

    if match := re.match(r"!points\s+([-+]?\d+)\s+.*", message.content):
        if message.author.id not in valid_user_ids:
            await message.channel.send(f"Nice try {message.author.display_name} 🙄")
            return

        points = int(match.group(1))
        for member in message.mentions:
            db_manager.add_member_points(member.id, points)

        await message.channel.send(f"Guild points set")

        return

    if message.content.startswith("!points"):
        s = "🏆 Guild Points 🏆"
        points = db_manager.get_member_points(message.author.id)
        s += f"\n{message.author.display_name} --> {points}"
        for member in message.mentions:
            if member.id == message.author.id:
                continue
            points = db_manager.get_member_points(member.id)
            s += f"\n{member.display_name} --> {points}"
        await message.channel.send(s[: config.DISCORD_MAX_MESSAGE_LENGTH])


async def handle_context_command(message, server_id):
    """Handles the !context command."""
    context = db_manager.get_recent_messages(server_id, config.CONTEXT_SIZE)
    context_str = "\n".join([f"{m['role']}: {m['content']}" for m in context]) or "None"
    await message.channel.send(context_str[-config.DISCORD_MAX_MESSAGE_LENGTH :])


async def handle_system_command(message, server_id):
    """Handles the !system command."""
    system_prompt = db_manager.get_system_prompt(server_id)
    system_str = f"System: {system_prompt['content']}"
    await message.channel.send(system_str[: config.DISCORD_MAX_MESSAGE_LENGTH])


async def handle_set_system_command(message, server_id):
    """Handles the !set_system command."""
    system_prompt_content = message.content.replace("!set_system", "").strip()
    db_manager.write_system_prompt(server_id, system_prompt_content)
    await message.channel.send("System prompt set")


async def handle_exec_command(message):
    """Execute command on the host shell"""
    if message.author.id == config.ADMIN2_USER_ID:
        command = message.content.replace("!exec", "").strip()
        try:
            output = subprocess.check_output(command, shell=True).decode("utf-8")
            await message.channel.send(
                f"```{output}"[: config.DISCORD_MAX_MESSAGE_LENGTH - 3] + "```"
            )
        except Exception as e:
            await message.channel.send(
                f"```{e}"[: config.DISCORD_MAX_MESSAGE_LENGTH - 3] + "```"
            )
    else:
        await message.channel.send("You do not have permission to execute commands ❌")


async def handle_help_command(message):
    await message.channel.send(
        """
    !system :: Print the system prompt
!system_set <text> :: Set the system prompt
!event <optional question> :: Get information about upcoming events. Optional text to ask questions about upcoming events
!points @user1 @user2 ... :: Get guild points for the requested users including the sender
!points <value> @user1 @user2 ... :: Add guild points for the requested users, only available for admins
@CFMB <text> :: Mention @CFMB to trigger the CFMB LLM; alternatively reply to a message from CFMB to trigger
    """
    )


async def handle_event_command(message, server_id):
    message.content = (
        "Tell me about events at https://www.meetup.com/cape-fear-makers-guild-meetup-group/ "
        + message.content[7:]
    )
    await handle_bot_mention(message, server_id)


async def handle_bot_mention(message, server_id):
    """Handles messages where the bot is mentioned."""
    print("Fetching context...")
    user_content = message.content.replace(str(config.BOT_USER_ID), "Maker bot")
    db_manager.write_message(server_id, "user", user_content)

    context_messages = db_manager.get_recent_messages(server_id, config.CONTEXT_SIZE)
    system_prompt = db_manager.get_system_prompt(server_id)
    context_messages.insert(0, system_prompt)

    if url := extract_first_url(user_content):
        print("Pulling web text...")
        url_text = get_webpage_text(url)
        context_messages.append({"role": "tool", "content": url_text})

    print("Running llm...")
    bot_response_content = llm_client.get_completion(context_messages)

    if bot_response_content:
        print("Writing context")
        db_manager.write_message(server_id, "assistant", bot_response_content)
        await message.channel.send(
            bot_response_content[: config.DISCORD_MAX_MESSAGE_LENGTH]
        )
    else:
        await message.channel.send(
            "Sorry, I encountered an error generating a response."
        )


if __name__ == "__main__":
    client.run(config.DISCORD_BOT_TOKEN)
