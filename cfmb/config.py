from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_HANDBOOK_URLS = (
    "https://wiki.capefearmakersguild.org/makerspace-rules,"
    "https://wiki.capefearmakersguild.org/personnel,"
    "https://wiki.capefearmakersguild.org/en/machines/bambu-3d-printers,"
    "https://wiki.capefearmakersguild.org/en/machines/carvera-cnc,"
    "https://wiki.capefearmakersguild.org/en/machines/omtech-co2-laser,"
    "https://wiki.capefearmakersguild.org/en/machines/omtech-fiber-laser"
)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file="~/.cfmb", env_file_encoding="utf-8", extra="ignore")

    # Discord
    DISCORD_BOT_TOKEN: str
    BOT_USER_ID: str
    DB_NAME: str
    DISCORD_MAX_MESSAGE_LENGTH: int = 2000
    DEV_CHANNEL_ID: int = 0
    DEV_EXCLUDED_CHANNELS: str = ""

    # LLM — OpenRouter primary, Ollama fallback
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str
    OLLAMA_MODEL: str = "gemma3:4b"

    # Web context
    MEETUP_URL: str = "https://www.meetup.com/cfmakers/events/?type=upcoming"
    HANDBOOK_URLS: str = _DEFAULT_HANDBOOK_URLS

    # Token budgets (all comfortably large — 128K context available)
    MEETUP_EVENT_COUNT: int = 100
    HANDBOOK_TOKEN_BUDGET: int = 100000
    DISCORD_CONTENT_TOKEN_BUDGET: int = 100000
    CHAIN_TOKEN_BUDGET: int = 10000

    # Ollama sampler params (fallback path)
    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.9
    LLM_TOP_K: int = 40
    LLM_MIN_P: float = 0.0
    LLM_PRESENCE_PENALTY: float = 0.0
    LLM_REPEAT_PENALTY: float = 1.1
    LLM_NUM_CTX: int = 131072

    LLM_TIMEOUT_SECONDS: int = 300
    LLM_TIMEOUT_MESSAGE: str = "Sorry, I took too long to respond. Try again."


config = Config()
