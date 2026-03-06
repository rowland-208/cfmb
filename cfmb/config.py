import os
from typing import Optional

from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.cfmb"))


class Config(BaseModel):
    DISCORD_BOT_TOKEN: str
    OLLAMA_MODEL: str
    BOT_USER_ID: str
    DB_NAME: str
    NUM_CLOSEST_MESSAGES: int
    DISCORD_MAX_MESSAGE_LENGTH: int
    ADMIN1_USER_ID: int
    ADMIN2_USER_ID: int
    OLLAMA_IMAGE_MODEL: Optional[str] = None
    OLLAMA_EMBEDDING_MODEL: Optional[str] = None
    NEWSLETTER_CHANNEL_ID: int
    NEWSLETTER_HOUR_ET: int = 10
    BOT_DISPLAY_NAME: str = "Bot"
    NEWSLETTER_TITLE: str = "Daily Newsletter"
    MEETUP_URL: Optional[str] = None
    SUMMARY_SYSTEM_PROMPT: str = (
        "You are a guild update assistant. "
        "Given a transcript of Discord messages from a single channel, "
        "write a 3-5 sentence summary in a newsletter/update style that highlights "
        "key events, announcements, projects, or discussions. "
        "Be concise and informative. Do not list every message — extract what matters. "
        "Do not include a title, heading, or channel name at the top — jump straight into the summary."
    )
    CURATION_SYSTEM_PROMPT: str = (
        "You are a newsletter editor. "
        "You will be given a set of Discord channel summaries, each with a heading and summary text. "
        "Select the three summaries that contain information other members are most likely to find useful. "
        "Deprioritize summaries that are primarily casual conversation, small talk, or lack substantive content. "
        "Return only those three summaries, in order from most to least relevant, "
        "preserving each channel's heading, summary text, and links exactly as given. "
        "Do not add commentary, preamble, or any other text."
    )

    @field_validator(
        "NUM_CLOSEST_MESSAGES",
        "DISCORD_MAX_MESSAGE_LENGTH",
        "ADMIN1_USER_ID",
        "ADMIN2_USER_ID",
        "NEWSLETTER_CHANNEL_ID",
        "NEWSLETTER_HOUR_ET",
        mode="before",
    )
    def _validate_int(cls, value):
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                raise ValueError(f"Invalid integer value: {value}")
        return value

    @classmethod
    def readenv(cls):
        return Config(
            DISCORD_BOT_TOKEN=os.environ["DISCORD_BOT_TOKEN"],
            OLLAMA_MODEL=os.environ["OLLAMA_MODEL"],
            BOT_USER_ID=os.environ["BOT_USER_ID"],
            DB_NAME=os.environ["DB_NAME"],
            NUM_CLOSEST_MESSAGES=os.environ["NUM_CLOSEST_MESSAGES"],
            DISCORD_MAX_MESSAGE_LENGTH=os.environ["DISCORD_MAX_MESSAGE_LENGTH"],
            ADMIN1_USER_ID=os.environ["ADMIN1_USER_ID"],
            ADMIN2_USER_ID=os.environ["ADMIN2_USER_ID"],
            OLLAMA_IMAGE_MODEL=os.environ.get("OLLAMA_IMAGE_MODEL") or None,
            OLLAMA_EMBEDDING_MODEL=os.environ.get("OLLAMA_EMBEDDING_MODEL") or None,
            NEWSLETTER_CHANNEL_ID=os.environ["NEWSLETTER_CHANNEL_ID"],
            NEWSLETTER_HOUR_ET=os.environ.get("NEWSLETTER_HOUR_ET", 10),
            BOT_DISPLAY_NAME=os.environ.get("BOT_DISPLAY_NAME", "Bot"),
            NEWSLETTER_TITLE=os.environ.get("NEWSLETTER_TITLE", "Daily Newsletter"),
            MEETUP_URL=os.environ.get("MEETUP_URL") or None,
            SUMMARY_SYSTEM_PROMPT=os.environ.get("SUMMARY_SYSTEM_PROMPT", Config.model_fields["SUMMARY_SYSTEM_PROMPT"].default),
            CURATION_SYSTEM_PROMPT=os.environ.get("CURATION_SYSTEM_PROMPT", Config.model_fields["CURATION_SYSTEM_PROMPT"].default),
        )


config = Config.readenv()
