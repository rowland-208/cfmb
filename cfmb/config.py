from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file="~/.cfmb", env_file_encoding="utf-8", extra="ignore")

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
    DEV_CHANNEL_ID: int
    DEV_EXCLUDED_CHANNELS: str = ""
    BRAVE_SEARCH_API_KEY: str
    LLM_TEMPERATURE: float
    LLM_TOP_P: float
    LLM_TOP_K: int
    LLM_MIN_P: float
    LLM_PRESENCE_PENALTY: float
    LLM_REPEAT_PENALTY: float
    FAST_MODEL: str = ""


config = Config()
