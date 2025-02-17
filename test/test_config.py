import os
import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from cfmb.config import Config


def test_config_valid_env_vars(mocker: MockerFixture):
    mocker.patch.dict(
        os.environ,
        {
            "DISCORD_BOT_TOKEN": "test_token",
            "OLLAMA_MODEL": "test_model",
            "BOT_USER_ID": "test_bot_user",
            "DB_NAME": "test_db",
            "CONTEXT_SIZE": "10",
            "DISCORD_MAX_MESSAGE_LENGTH": "200",
            "ADMIN1_USER_ID": "123",
            "ADMIN2_USER_ID": "456",
        },
    )
    config = Config.readenv()

    assert config.DISCORD_BOT_TOKEN == "test_token"
    assert config.OLLAMA_MODEL == "test_model"
    assert config.BOT_USER_ID == "test_bot_user"
    assert config.DB_NAME == "test_db"
    assert config.CONTEXT_SIZE == 10
    assert config.DISCORD_MAX_MESSAGE_LENGTH == 200
    assert config.ADMIN1_USER_ID == 123
    assert config.ADMIN2_USER_ID == 456


def test_config_invalid_int_value(mocker: MockerFixture):
    mocker.patch.dict(os.environ, {"CONTEXT_SIZE": "invalid"})

    with pytest.raises(ValidationError):
        config = Config.readenv()


def test_config_missing_env_var(mocker: MockerFixture):
    mocker.patch.dict(os.environ, {}, clear=True)

    with pytest.raises(KeyError):
        config = Config.readenv()
