import asyncio
import pathlib
import sys

import discord

from cfmb.budget import cap_rows
from cfmb.config import config
from cfmb.db_manager import DatabaseManager
from cfmb.llm_client import LLMClient
from cfmb.prompt import build_chain_messages, build_system_prompt, render_discord_content
from cfmb.web_context import fetch_handbook_markdown, fetch_meetup_markdown


ACTIVE_FILE = pathlib.Path("/tmp/cfmb_active")
BASE_PROMPT_PATH = pathlib.Path(__file__).parent.parent / "etc" / "base_system.md"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
db = DatabaseManager(config.DB_NAME)
llm = LLMClient(
    openrouter_model=config.OPENROUTER_MODEL,
    openrouter_api_key=config.OPENROUTER_API_KEY,
    ollama_model=config.OLLAMA_MODEL,
)
llm_queue: asyncio.Queue = asyncio.Queue()
_base_prompt = ""
_handbook_urls: list[str] = []


@client.event
async def on_ready():
    global _base_prompt, _handbook_urls
    db.initialize_db()
    _base_prompt = BASE_PROMPT_PATH.read_text()
    _handbook_urls = [u.strip() for u in config.HANDBOOK_URLS.split(",") if u.strip()]
    client.loop.create_task(llm_worker())
    if config.DEV_CHANNEL_ID:
        ch = client.get_channel(config.DEV_CHANNEL_ID)
        if ch:
            await ch.send("CFMB online")
    print(f"Bot online as {client.user}", flush=True)


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.guild is None:
        await message.channel.send("I can only respond in servers.")
        return

    reply_to = str(message.reference.message_id) if message.reference else None
    # mentioned_in covers user, role, and @everyone — most servers tag bots by role.
    is_mention = bool(message.guild.me and message.guild.me.mentioned_in(message))
    bot_id_str = str(config.BOT_USER_ID)

    chain_id = db.write_message(
        server_id=str(message.guild.id),
        message_id=str(message.id),
        user_id=str(message.author.id),
        username=message.author.display_name,
        channel_id=str(message.channel.id),
        channel_name=getattr(message.channel, "name", None),
        content=message.content,
        reply_to_message_id=reply_to,
        is_mention=is_mention,
        bot_user_id=bot_id_str,
    )

    is_reply_to_bot = bool(reply_to) and db.is_message_from_user(reply_to, bot_id_str)
    if is_mention or is_reply_to_bot:
        await llm_queue.put((message, chain_id))
        print(f"Enqueued LLM request (queue size: {llm_queue.qsize()})", flush=True)


async def llm_worker():
    while True:
        message, chain_id = await llm_queue.get()
        try:
            ACTIVE_FILE.touch()
            async with asyncio.timeout(config.LLM_TIMEOUT_SECONDS):
                await process_llm_request(message, chain_id)
        except TimeoutError:
            print("LLM request timed out", file=sys.stderr, flush=True)
            try:
                await message.reply(config.LLM_TIMEOUT_MESSAGE)
            except Exception as e:
                print(f"reply on timeout failed: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"LLM request error: {e}", file=sys.stderr, flush=True)
        finally:
            ACTIVE_FILE.unlink(missing_ok=True)
            llm_queue.task_done()


async def process_llm_request(message, chain_id):
    server_id = str(message.guild.id)
    excluded = [c.strip() for c in config.DEV_EXCLUDED_CHANNELS.split(",") if c.strip()]

    # Start the typing indicator before the (slow) web fetches + LLM call so it
    # shows up promptly rather than after context assembly.
    async with message.channel.typing():
        discord_rows = db.get_recent_discord_messages(
            server_id=server_id,
            current_chain_id=chain_id,
            excluded_channel_ids=excluded,
            days=7,
        )
        discord_rows = cap_rows(discord_rows, config.DISCORD_CONTENT_TOKEN_BUDGET)
        discord_rows.reverse()

        chain_rows = db.get_chain_messages(chain_id) if chain_id else []
        chain_capped_rev = cap_rows(list(reversed(chain_rows)), config.CHAIN_TOKEN_BUDGET)
        chain_rows = list(reversed(chain_capped_rev))

        loop = asyncio.get_event_loop()
        meetup_md, handbook_md = await asyncio.gather(
            loop.run_in_executor(None, fetch_meetup_markdown, config.MEETUP_URL, config.MEETUP_EVENT_COUNT),
            loop.run_in_executor(None, fetch_handbook_markdown, _handbook_urls, config.HANDBOOK_TOKEN_BUDGET),
        )

        discord_md = render_discord_content(discord_rows)
        system_prompt = build_system_prompt(
            base=_base_prompt, meetup=meetup_md, handbook=handbook_md, discord=discord_md,
        )
        chain_messages = build_chain_messages(chain_rows, str(config.BOT_USER_ID))
        messages = [{"role": "system", "content": system_prompt}, *chain_messages]

        print(f"Calling LLM ({len(messages)} messages, "
              f"~{len(system_prompt) // 4} sys tokens, "
              f"{len(chain_messages)} chain turns)", flush=True)

        reply_text = await llm.get_completion(messages)

    if not reply_text:
        await message.reply("Sorry, I had an error responding.")
        return

    reply = await message.reply(reply_text[: config.DISCORD_MAX_MESSAGE_LENGTH])
    db.write_message(
        server_id=server_id,
        message_id=str(reply.id),
        user_id=str(config.BOT_USER_ID),
        username=client.user.display_name if client.user else "bot",
        channel_id=str(message.channel.id),
        channel_name=getattr(message.channel, "name", None),
        content=reply_text,
        reply_to_message_id=str(message.id),
        is_mention=False,
        bot_user_id=str(config.BOT_USER_ID),
        chain_id_override=chain_id,
    )


if __name__ == "__main__":
    client.run(config.DISCORD_BOT_TOKEN)
