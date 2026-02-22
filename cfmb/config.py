import os
from typing import Optional

from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

load_dotenv()


class Config(BaseModel):
    DISCORD_BOT_TOKEN: str
    OLLAMA_MODEL: str
    BOT_USER_ID: str
    DB_NAME: str
    CONTEXT_SIZE: int
    DISCORD_MAX_MESSAGE_LENGTH: int
    ADMIN1_USER_ID: int
    ADMIN2_USER_ID: int
    OLLAMA_IMAGE_MODEL: Optional[str] = None

    @field_validator(
        "CONTEXT_SIZE",
        "DISCORD_MAX_MESSAGE_LENGTH",
        "ADMIN1_USER_ID",
        "ADMIN2_USER_ID",
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
            CONTEXT_SIZE=os.environ["CONTEXT_SIZE"],
            DISCORD_MAX_MESSAGE_LENGTH=os.environ["DISCORD_MAX_MESSAGE_LENGTH"],
            ADMIN1_USER_ID=os.environ["ADMIN1_USER_ID"],
            ADMIN2_USER_ID=os.environ["ADMIN2_USER_ID"],
            OLLAMA_IMAGE_MODEL=os.environ.get("OLLAMA_IMAGE_MODEL") or None,
        )


config = Config.readenv()
