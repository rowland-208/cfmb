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
    SUMMARY_SYSTEM_PROMPT: str
    CURATION_SYSTEM_PROMPT: str
    NEWSLETTER_EXCLUDED_CHANNELS: str = ""

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
            SUMMARY_SYSTEM_PROMPT=os.environ["SUMMARY_SYSTEM_PROMPT"],
            CURATION_SYSTEM_PROMPT=os.environ["CURATION_SYSTEM_PROMPT"],
            NEWSLETTER_EXCLUDED_CHANNELS=os.environ.get("NEWSLETTER_EXCLUDED_CHANNELS", ""),
        )


config = Config.readenv()
