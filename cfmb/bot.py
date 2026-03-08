import asyncio
import io
import pathlib
import re
import subprocess
import math
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from discord.ext import tasks

from PIL import Image

ACTIVE_FILE = pathlib.Path("/tmp/cfmb_active")

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
llm_queue = asyncio.Queue()
llm_worker_task = None
emoji_queue = asyncio.Queue()
emoji_worker_task = None

# Matches common Unicode emoji ranges
EMOJI_PATTERN = re.compile(
    "[\U0001F000-\U0001FFFF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "]+"
)


NOON_EASTERN = time(config.NEWSLETTER_HOUR_ET, 0, tzinfo=ZoneInfo("America/New_York"))
FOUR_AM_EASTERN = time(4, 0, tzinfo=ZoneInfo("America/New_York"))


@client.event
async def on_ready():
    global llm_worker_task, emoji_worker_task
    db_manager.initialize_db()
    llm_worker_task = client.loop.create_task(llm_worker())
    emoji_worker_task = client.loop.create_task(emoji_reaction_worker())
    daily_summary.start()
    daily_profiles.start()
    print(f"Bot is online as {client.user}!")


@tasks.loop(time=NOON_EASTERN)
async def daily_summary():
    channel = client.get_channel(config.NEWSLETTER_CHANNEL_ID)
    if not channel:
        print("Daily summary: newsletter channel not found.")
        return
    server_id = str(channel.guild.id)
    await post_summaries(server_id, channel)


def _build_profile_prompt(username, transcript):
    """Returns an Ollama-compatible message list for generating a user profile."""
    return [
        {
            "role": "system",
            "content": (
                "You are a text analysis tool. Your only job is to output a structured member profile "
                "based on the chat transcript provided. Do not greet the user. Do not ask questions. "
                "Do not respond as an assistant or chatbot. Do not use phrases like 'I'm here to help'. "
                "Output ONLY the profile, exactly in this format:\n\n"
                "<3-5 sentences about interests and conversation style>\n\n"
                "**Top 3 facts, projects, and ideas:**\n"
                "- <fact or project 1>\n"
                "- <fact or project 2>\n"
                "- <fact or project 3>\n\n"
                "The bulleted list must have exactly 3 items — no more, no fewer."
            ),
        },
        {
            "role": "user",
            "content": f"Transcript of messages from '{username}':\n\n{transcript}",
        },
    ]


@tasks.loop(time=FOUR_AM_EASTERN)
async def daily_profiles():
    """Generates and persists a profile for every active user from the past week."""
    channel = client.get_channel(config.NEWSLETTER_CHANNEL_ID)
    if not channel:
        print("Daily profiles: newsletter channel not found.")
        return
    server_id = str(channel.guild.id)
    users = db_manager.get_active_users_7d(server_id)
    id_to_name = db_manager.get_user_id_name_map(server_id)
    id_to_name[str(config.BOT_USER_ID)] = config.BOT_DISPLAY_NAME
    print(f"Daily profiles: generating profiles for {len(users)} users.")
    for user in users:
        user_id = user["user_id"]
        username = user["username"]
        raw = db_manager.get_raw_messages_by_user_7d(server_id, user_id)
        if len(raw) < 20:
            continue
        transcript = "\n".join(
            f"[{m['channel_name'] or 'unknown'}] {_resolve_mentions(m['content'], id_to_name)}"
            for m in raw
            if m["content"].strip()
        )
        prompt = _build_profile_prompt(username, transcript)
        profile = await llm_client.get_completion(prompt)
        if profile:
            db_manager.write_user_profile(server_id, user_id, username, profile)
            print(f"Daily profiles: saved profile for {username}.")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.guild is None:
        await message.channel.send("I can only respond to messages in servers.")
        return

    server_id = str(message.guild.id)
    db_manager.write_raw_message(
        server_id,
        str(message.id),
        str(message.author.id),
        message.author.display_name,
        message.content,
        channel_id=str(message.channel.id),
        channel_name=message.channel.name,
    )
    if config.OLLAMA_EMBEDDING_MODEL and message.content:
        id_to_name = db_manager.get_user_id_name_map(server_id)
        id_to_name[str(config.BOT_USER_ID)] = config.BOT_DISPLAY_NAME
        asyncio.ensure_future(_store_embedding(str(message.id), _resolve_mentions(message.content, id_to_name)))

    chain_id = resolve_chain_id(message)

    if "NVDA" in message.content:
        await message.add_reaction("👀")

    await emoji_queue.put(message)

    if message.content.startswith("/context"):
        await handle_context_command(message, server_id, chain_id)
        return

    if message.content.startswith("/events"):
        await handle_event_command(message, server_id, chain_id)
        return

    if message.content.startswith("/help"):
        await handle_help_command(message)
        return

    if message.content.startswith("/points"):
        await handle_guild_points_command(message)
        return

    if message.content.startswith("/system"):
        await handle_system_command(message, server_id)
        return

    if message.content.startswith("/set_system"):
        await handle_set_system_command(message, server_id)
        return

    if message.content.startswith("/exec"):
        await handle_exec_command(message)
        return

    if message.content.startswith("/generate"):
        await handle_generate_command(message)
        return

    if message.content.startswith("/recall"):
        await handle_recall_command(message, server_id)
        return

    if message.content.startswith("/preview"):
        await handle_preview_command(message, server_id)
        return

    if message.content.startswith("/profile_gen"):
        await handle_profile_gen_command(message, server_id)
        return

    if message.content.startswith("/profile"):
        await handle_profile_command(message, server_id)
        return

    if message.content.startswith("/search"):
        await handle_search_command(message, server_id)
        return

    if message.content.startswith("/summary"):
        await handle_summary_command(message, server_id)
        return

    if message.content.startswith("/unhinged"):
        message.content = message.content.replace("/unhinged", "", 1).strip()
        await handle_bot_mention(message, server_id, chain_id, skip_moderation=True)
        return

    if client.user in message.mentions:
        await handle_bot_mention(message, server_id, chain_id)
        return



async def handle_guild_points_command(message):
    valid_user_ids = (config.ADMIN1_USER_ID, config.ADMIN2_USER_ID)

    if match := re.match(r"/points\s+([-+]?\d+)\s+.*", message.content):
        if message.author.id not in valid_user_ids:
            await message.channel.send(f"Nice try {message.author.display_name} 🙄")
            return

        points = int(match.group(1))
        for member in message.mentions:
            db_manager.add_member_points(member.id, points)

        await message.channel.send(f"Guild points set")

        return

    if message.content.startswith("/points"):
        s = "🏆 Guild Points 🏆"
        points = db_manager.get_member_points(message.author.id)
        s += f"\n{message.author.display_name} --> {points}"
        for member in message.mentions:
            if member.id == message.author.id:
                continue
            points = db_manager.get_member_points(member.id)
            s += f"\n{member.display_name} --> {points}"
        await message.channel.send(s[: config.DISCORD_MAX_MESSAGE_LENGTH])


async def handle_context_command(message, server_id, chain_id):
    """Handles the /context command."""
    recent_chains = db_manager.get_recent_chains(server_id, limit=4)
    if not recent_chains:
        await message.channel.send("None")
        return
    lines = []
    for cid in recent_chains:
        marker = " (current)" if cid == chain_id else ""
        lines.append(f"--- {cid}{marker} ---")
        messages = db_manager.get_recent_messages(server_id, cid, limit=6)
        for m in messages:
            content = m["content"].replace("\t", " ").replace("\n", " ")
            words = content.split(" ")
            snippet = " ".join(words[:5]) + " ... " + " ".join(words[-5:]) if len(words) > 10 else content
            label = m["username"] or m["role"]
            ch_name = m["channel_name"] or ""
            ch_id = m["channel_id"] or ""
            ch = f"{ch_name} ...{ch_id[-5:]}" if ch_id else ch_name
            lines.append(f"{label} :: {ch} :: {snippet}")
    context_str = "\n".join(lines)
    await message.channel.send(context_str[-config.DISCORD_MAX_MESSAGE_LENGTH :])


async def handle_system_command(message, server_id):
    """Handles the /system command."""
    system_prompt = db_manager.get_system_prompt(server_id)
    system_str = f"System: {system_prompt['content']}"
    await message.channel.send(system_str[: config.DISCORD_MAX_MESSAGE_LENGTH])


async def handle_set_system_command(message, server_id):
    """Handles the /set_system command."""
    system_prompt_content = message.content.replace("/set_system", "").strip()
    db_manager.write_system_prompt(server_id, system_prompt_content)
    await message.channel.send("System prompt set")


async def handle_exec_command(message):
    """Execute command on the host shell"""
    if message.author.id == config.ADMIN2_USER_ID:
        command = message.content.replace("/exec", "").strip()
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


async def handle_recall_command(message, server_id):
    """Handles the /recall command — prints the last N raw messages."""
    arg = message.content.replace("/recall", "", 1).strip()
    try:
        limit = int(arg) if arg else 10
    except ValueError:
        await message.channel.send("Usage: `/recall [n]` — n must be an integer")
        return

    raw = db_manager.get_recent_raw_messages(server_id, limit)
    if not raw:
        await message.channel.send("No messages recorded yet.")
        return

    grouped = {}
    for m in raw:
        cid = m["channel_id"] or "unknown"
        grouped.setdefault(cid, []).append(m)

    lines = []
    for cid, msgs in grouped.items():
        ch_name = msgs[-1]["channel_name"] or ""
        ch_id_trim = cid[-5:] if cid != "unknown" else "unknown"
        lines.append(f"--- {ch_name} ...{ch_id_trim} ---")
        for m in msgs:
            content = m["content"].replace("\t", " ").replace("\n", " ")
            words = content.split(" ")
            snippet = " ".join(words[:5]) + " ... " + " ".join(words[-5:]) if len(words) > 10 else content
            lines.append(f"...{m['message_id'][-5:]} :: {m['username']} :: {snippet}")

    await message.channel.send("\n".join(lines)[-config.DISCORD_MAX_MESSAGE_LENGTH:])


async def handle_preview_command(message, server_id):
    """Handles /preview <text> — builds and prints the full system prompt without calling the LLM."""
    user_text = message.content.replace("/preview", "", 1).strip()
    if not user_text:
        await message.channel.send("Usage: `/preview <message text>`")
        return

    id_to_name = db_manager.get_user_id_name_map(server_id)
    id_to_name[str(config.BOT_USER_ID)] = config.BOT_DISPLAY_NAME
    async with message.channel.typing():
        system_prompt = await _build_system_prompt(message, server_id, user_text, id_to_name)

    content = system_prompt["content"]
    chunk_size = 1950
    for i in range(0, len(content), chunk_size):
        await message.channel.send(f"```{content[i:i + chunk_size]}```")


async def handle_profile_gen_command(message, server_id):
    """Handles /profile_gen — generates a profile on the fly without reading or writing the DB."""
    target = message.mentions[0] if message.mentions else message.author
    username = target.display_name

    raw = db_manager.get_raw_messages_by_user_7d(server_id, target.id)
    if len(raw) < 20:
        await message.channel.send(f"Not enough messages to generate a profile for **{username}** (need at least 20 in the past week).")
        return

    id_to_name = db_manager.get_user_id_name_map(server_id)
    id_to_name[str(config.BOT_USER_ID)] = config.BOT_DISPLAY_NAME
    transcript = "\n".join(
        f"[{m['channel_name'] or 'unknown'}] {_resolve_mentions(m['content'], id_to_name)}"
        for m in raw
        if m["content"].strip()
    )

    prompt = _build_profile_prompt(username, transcript)
    async with message.channel.typing():
        profile = await llm_client.get_completion(prompt)

    if not profile:
        await message.channel.send("Failed to generate profile.")
        return

    await message.channel.send(f"## User profile\n{profile}"[: config.DISCORD_MAX_MESSAGE_LENGTH])


async def handle_profile_command(message, server_id):
    """Handles the /profile command — fetches the latest saved profile for a user."""
    target = message.mentions[0] if message.mentions else message.author
    username = target.display_name

    row = db_manager.get_latest_user_profile(server_id, target.id)
    if not row:
        await message.channel.send(f"No profile found for **{username}**. Profiles are generated nightly.")
        return

    created_at = row["created_at"]
    await message.channel.send(f"{row['profile']}\n\n*Generated: {created_at}*"[: config.DISCORD_MAX_MESSAGE_LENGTH])


async def handle_search_command(message, server_id):
    """Handles the /search command — finds the 3 most semantically similar messages."""
    if not config.OLLAMA_EMBEDDING_MODEL:
        await message.channel.send("Search is not configured (no `OLLAMA_EMBEDDING_MODEL` set).")
        return

    query = message.content.replace("/search", "", 1).strip()
    if not query:
        await message.channel.send("Usage: `/search <text>`")
        return

    async with message.channel.typing():
        embedding = await llm_client.get_embedding(query, config.OLLAMA_EMBEDDING_MODEL)

    if not embedding:
        await message.channel.send("Failed to generate embedding for your query.")
        return

    results = db_manager.search_messages(server_id, embedding, limit=3)
    if not results:
        await message.channel.send("No results found.")
        return

    lines = [f"**Results for** `{query[:50]}`"]
    for r in results:
        snippet = r["content"][:20].replace("\n", " ")
        url = f"https://discord.com/channels/{server_id}/{r['channel_id']}/{r['message_id']}"
        lines.append(f"**{r['username']}** · [{snippet}…]({url})")

    await message.channel.send("\n".join(lines))


async def handle_summary_command(message, server_id):
    """Summarizes the past 24 hours of messages per channel."""
    raw = db_manager.get_raw_messages_24h(server_id)
    if not raw:
        await message.channel.send("No messages in the past 24 hours.")
        return
    await post_summaries(server_id, message.channel)


async def post_summaries(server_id, channel):
    """Generates and posts per-channel summaries for the past 24 hours."""
    raw = db_manager.get_raw_messages_24h(server_id)
    if not raw:
        await channel.send("No messages in the past 24 hours.")
        return

    today = date.today().isoformat()
    header = f"# {config.NEWSLETTER_TITLE}\n{today}"

    channels = {}
    for m in raw:
        cid = m["channel_id"] or "unknown"
        channels.setdefault(cid, {"name": m["channel_name"] or cid, "messages": []})
        channels[cid]["messages"].append(m)

    def _clean_content(text):
        # Remove Discord mention syntax (<@123>, <@!123>, <#123>, <@&123>)
        text = re.sub(r"<[@#][!&]?\d+>", "", text)
        # Remove any remaining @ symbols
        return text.replace("@", "")

    # Generate each channel summary and find sources in one pass
    excluded = set(config.NEWSLETTER_EXCLUDED_CHANNELS.split(",")) if config.NEWSLETTER_EXCLUDED_CHANNELS else set()
    channel_blocks = []
    for cid, data in channels.items():
        if cid in excluded:
            continue
        ch_name = data["name"]
        transcript = "\n".join(
            f"{m['username']}: {_clean_content(m['content'])}" for m in data["messages"]
        )
        summary_prompt = [
            {
                "role": "system",
                "content": config.SUMMARY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": f"Summarize the following messages from #{ch_name}:\n\n{transcript}",
            },
        ]
        async with channel.typing():
            summary = await llm_client.get_completion(summary_prompt)
        if not summary:
            continue

        # Build channel block: heading then summary
        block = f"**#{ch_name}**\n{summary.strip()}"
        channel_blocks.append(block)

    if not channel_blocks:
        await channel.send(header)
        return

    # Combine all channel blocks for the curation editor
    combined = "\n\n".join(channel_blocks)

    curation_prompt = [
        {
            "role": "system",
            "content": config.CURATION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": f"Here are the channel summaries:\n\n{combined}",
        },
    ]

    async with channel.typing():
        curated = await llm_client.get_completion(curation_prompt)

    if curated:
        curated = curated.replace("@", "")

        if config.OLLAMA_EMBEDDING_MODEL:
            curated = await _annotate_with_sources(curated, server_id)

        dad_joke_prompt = [
            {
                "role": "system",
                "content": (
                    "You are a dad joke generator. "
                    "Given a newsletter summary, respond with a single one-liner dad joke related to its content. "
                    "Output only the joke — no explanation, no preamble, no quotation marks."
                ),
            },
            {
                "role": "user",
                "content": curated.strip(),
            },
        ]
        async with channel.typing():
            dad_joke = await llm_client.get_completion(dad_joke_prompt)

        await channel.send(header)
        sections = [s.strip() for s in re.split(r'(?=\*\*#)', curated.strip()) if s.strip()]
        if not sections:
            sections = [curated.strip()]
        for section in sections:
            await channel.send(section[: config.DISCORD_MAX_MESSAGE_LENGTH])
        if dad_joke:
            await channel.send(f"*{dad_joke.strip()}*")
    else:
        await channel.send(header)


async def _annotate_with_sources(text: str, server_id: str) -> str:
    """Splits summary text by punctuation and newlines, finds a source message for each segment
    with 5+ words, and inserts an inline source link before the closing punctuation."""
    parts = re.split(r'([.,;:!?\n])', text)
    result = []
    counter = 0
    i = 0
    while i < len(parts):
        segment = parts[i]
        delimiter = parts[i + 1] if i + 1 < len(parts) else ''
        result.append(segment)
        if len(segment.split()) >= 5:
            embedding = await llm_client.get_embedding(segment.strip(), config.OLLAMA_EMBEDDING_MODEL)
            if embedding:
                matches = db_manager.search_messages(server_id, embedding, limit=1, hours=24)
                if matches and matches[0]['distance'] < 0.408 and matches[0].get('channel_id'):
                    r = matches[0]
                    url = f"https://discord.com/channels/{server_id}/{r['channel_id']}/{r['message_id']}"
                    counter += 1
                    result.append(f" [[{counter}]]({url})")
        result.append(delimiter)
        i += 2
    return ''.join(result)


async def handle_generate_command(message):
    """Generates an image from a text prompt using Ollama and posts it to the channel."""
    if not config.OLLAMA_IMAGE_MODEL:
        await message.channel.send(
            "Image generation is not configured. "
            "Ask an admin to set the `OLLAMA_IMAGE_MODEL` environment variable (e.g. `x/flux2-klein`)."
        )
        return

    prompt = message.content.replace("/generate", "", 1).strip()
    if not prompt:
        await message.channel.send("Please provide a prompt: `/generate <description>`")
        return

    async with message.channel.typing():
        image_bytes = await llm_client.generate_image(prompt, config.OLLAMA_IMAGE_MODEL)

    if image_bytes:
        file = discord.File(io.BytesIO(image_bytes), filename="generated.png")
        await message.channel.send(file=file)
    else:
        await message.channel.send("Sorry, I encountered an error generating the image.")


async def handle_help_command(message):
    await message.channel.send(
        """
    /system :: Print the system prompt
/set_system <text> :: Set the system prompt
/event <optional question> :: Get information about upcoming events. Optional text to ask questions about upcoming events
/generate <description> :: Generate an image from a text description
/recall [n] :: Print the last n messages in this server (default 10)
/search <text> :: Semantic search — find the 3 most relevant past messages
/summary :: Summarize the past 24 hours of messages by channel
/points @user1 @user2 ... :: Get guild points for the requested users including the sender
/points <value> @user1 @user2 ... :: Add guild points for the requested users, only available for admins
@CFMB <text> :: Mention @CFMB to trigger the CFMB LLM; alternatively reply to a message from CFMB to trigger
/unhinged <text> :: Same as mentioning @CFMB but skips content moderation
    """
    )


async def handle_event_command(message, server_id, chain_id):
    prefix = f"Tell me about events at {config.MEETUP_URL} " if config.MEETUP_URL else ""
    message.content = prefix + message.content[7:]
    await handle_bot_mention(message, server_id, chain_id)


async def handle_bot_mention(message, server_id, chain_id, skip_moderation=True):
    """Enqueues a bot mention for LLM processing."""
    await llm_queue.put((message, server_id, chain_id, skip_moderation))
    print(f"Queue: added request (size: {llm_queue.qsize()})")


async def llm_worker():
    """Processes LLM requests from the queue one at a time."""
    while True:
        message, server_id, chain_id, skip_moderation = await llm_queue.get()
        print(f"Queue: processing request (size: {llm_queue.qsize()})")
        await asyncio.sleep(1)
        try:
            ACTIVE_FILE.touch()
            await process_llm_request(message, server_id, chain_id, skip_moderation=skip_moderation)
        except Exception as e:
            print(f"Error processing LLM request: {e}")
        finally:
            ACTIVE_FILE.unlink(missing_ok=True)
            llm_queue.task_done()


async def emoji_reaction_worker():
    """Processes emoji reaction requests from the queue one at a time."""
    while True:
        message = await emoji_queue.get()
        print(f"Emoji queue: processing (size: {emoji_queue.qsize()})")
        try:
            await process_emoji_reaction(message)
        except Exception as e:
            print(f"Error in emoji reaction worker: {e}")
        finally:
            emoji_queue.task_done()



async def process_emoji_reaction(message):
    """Asks the LLM to pick an emoji reaction (~1% of the time) or skip."""
    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are a Discord bot that reacts to messages with a single emoji. "
                "About 1% of the time respond with exactly one emoji character that fits the message. "
                "If the user seems excited, increase the odds of reacting to 10%. "
                "The other times respond with exactly the word 'next'. "
                "Prefer emojis like 😂❤️👏🧠⚒️🤘🚀🤖 but choose whichever fits best. "
                "Output only the emoji or the word 'next' — nothing else."
            ),
        },
        {"role": "user", "content": message.content},
    ]
    response = await llm_client.get_completion(prompt_messages)
    if not response:
        return
    match = EMOJI_PATTERN.search(response)
    if match:
        emoji = match.group(0)[0]
        try:
            await message.add_reaction(emoji)
            print(f"Emoji reaction: reacted with {emoji}")
        except Exception as e:
            print(f"Emoji reaction: failed to add reaction: {e}")


async def _store_embedding(message_id: str, content: str):
    """Fetches an embedding for content and persists it to the database."""
    embedding = await llm_client.get_embedding(content, config.OLLAMA_EMBEDDING_MODEL)
    if embedding:
        db_manager.write_message_embedding(message_id, embedding)


def resolve_chain_id(message):
    """Returns the chain_id for a message by traversing its reply chain."""
    if message.reference is None:
        return str(message.id)
    parent_chain_id = db_manager.get_chain_id(str(message.reference.message_id))
    return parent_chain_id if parent_chain_id else str(message.reference.message_id)


def _format_age(seconds):
    """Format an age in seconds as 'X days Y hours', rounded up to the nearest hour."""
    hours_total = math.ceil(seconds / 3600)
    days, hours = divmod(hours_total, 24)
    if days and hours:
        return f"{days} days {hours} hours"
    elif days:
        return f"{days} days"
    return f"{hours} hours"


def _resolve_mentions(text, id_to_name):
    """Replaces <@USER_ID> and <@!USER_ID> patterns with @username where known."""
    def replace(match):
        uid = match.group(1)
        return f"@{id_to_name[uid]}" if uid in id_to_name else match.group(0)
    return re.sub(r"<@!?(\d+)>", replace, text)


async def _build_system_prompt(message, server_id, user_content, id_to_name=None):
    """Constructs the full system prompt for a message, including RAG, profile, and metadata."""
    system_prompt = db_manager.get_system_prompt(server_id)

    now_utc = datetime.now(tz=timezone.utc)
    now_eastern = datetime.now(tz=ZoneInfo("America/New_York"))

    prev_ts = db_manager.get_previous_message_timestamp(server_id, message.author.id, str(message.id))
    prev_age = _format_age((now_utc - datetime.fromisoformat(prev_ts).replace(tzinfo=timezone.utc)).total_seconds()) if prev_ts else "inactive user"

    profile_row = db_manager.get_latest_user_profile(server_id, message.author.id)
    profile_age = _format_age((now_utc - datetime.fromisoformat(profile_row["created_at"]).replace(tzinfo=timezone.utc)).total_seconds()) if profile_row else "still learning"

    system_prompt["content"] += (
        f"\n\n## Metadata"
        f"\n- Channel name: #{message.channel.name}"
        f"\n- User name: {message.author.display_name}"
        f"\n- Current time: {now_eastern.strftime('%Y-%m-%dT%H:%M:%S')}"
        f"\n- User last active: {prev_age}"
    )

    if profile_row:
        system_prompt["content"] += f"\n\n## User profile\n{profile_row['profile']}"
    else:
        system_prompt["content"] += "\n\n## User profile\nThis user has not been active recently and no profile is available."

    if config.OLLAMA_EMBEDDING_MODEL:
        resolved_content = _resolve_mentions(user_content, id_to_name or {})
        embedding = await llm_client.get_embedding(resolved_content, config.OLLAMA_EMBEDDING_MODEL)
        if embedding:
            matches = db_manager.search_messages(server_id, embedding, limit=10, hours=48)
            if matches:
                lines = ["## Search results", "The following are the top matching messages from the past 48 hours related to this conversation:"]
                for r in matches:
                    content = _resolve_mentions(r['content'][:200], id_to_name or {}).replace("\n", " ")
                    lines.append(f"- [{r['channel_name'] or 'unknown'}] {r['username']}: {content}")
                system_prompt["content"] += "\n\n" + "\n".join(lines)

    recent_user_msgs = db_manager.get_recent_raw_messages_by_user(server_id, message.author.id, limit=5)
    if recent_user_msgs:
        lines = ["## Recent messages from this user"]
        for m in recent_user_msgs:
            content = _resolve_mentions(m['content'], id_to_name or {}).replace("\n", " ")
            lines.append(f"- [{m['channel_name'] or 'unknown'}] {content}")
        system_prompt["content"] += "\n\n" + "\n".join(lines)

    return system_prompt


async def process_llm_request(message, server_id, chain_id, skip_moderation=True):
    """Processes a single LLM request."""
    async with message.channel.typing():
        print("Fetching context...")
        id_to_name = db_manager.get_user_id_name_map(server_id)
        id_to_name[str(config.BOT_USER_ID)] = config.BOT_DISPLAY_NAME
        user_content = _resolve_mentions(message.content, id_to_name)

        if not skip_moderation:
            print("Moderating message...")
            mod_response = await llm_client.moderate(user_content)
            if mod_response and re.search(r"\bblock\b", mod_response, re.IGNORECASE):
                print(f"Moderation: blocked message from {message.author.display_name}")
                await message.add_reaction("⚠️")
                return

        db_manager.write_message(server_id, chain_id, "user", user_content, username=message.author.display_name, message_id=str(message.id), channel_id=str(message.channel.id), channel_name=message.channel.name, user_id=str(message.author.id))

        image_bytes_list = []
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                data = await attachment.read()
                if attachment.content_type == "image/gif":
                    frame = Image.open(io.BytesIO(data))
                    frame.seek(0)
                    buf = io.BytesIO()
                    frame.convert("RGB").save(buf, format="PNG")
                    data = buf.getvalue()
                image_bytes_list.append(data)

        context_messages = db_manager.get_recent_messages(server_id, chain_id, config.NUM_CLOSEST_MESSAGES)

        system_prompt = await _build_system_prompt(message, server_id, user_content, id_to_name)

        context_messages.insert(0, system_prompt)

        if image_bytes_list:
            context_messages[-1]["images"] = image_bytes_list

        if url := extract_first_url(user_content):
            print("Pulling web text...")
            url_text = get_webpage_text(url)
            context_messages.append({"role": "tool", "content": url_text})

        print("Running llm...")
        bot_response_content = await llm_client.get_completion(context_messages)

    if bot_response_content:
        print("Writing context")
        reply = await message.reply(bot_response_content[: config.DISCORD_MAX_MESSAGE_LENGTH])
        db_manager.write_message(server_id, chain_id, "assistant", bot_response_content, message_id=str(reply.id), channel_id=str(message.channel.id), channel_name=message.channel.name)
    else:
        await message.reply(
            "Sorry, I encountered an error generating a response."
        )


if __name__ == "__main__":
    client.run(config.DISCORD_BOT_TOKEN)
