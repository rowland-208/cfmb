import os

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from cfmb.config import Config


REQUIRED_ENV = {
    "DISCORD_BOT_TOKEN": "test-token",
    "BOT_USER_ID": "1234567890",
    "DB_NAME": "/tmp/test.sqlite",
    "OPENROUTER_API_KEY": "sk-or-test",
    "OPENROUTER_MODEL": "test/model",
}


def test_config_valid_env_vars(mocker: MockerFixture):
    mocker.patch.dict(os.environ, REQUIRED_ENV, clear=True)
    config = Config(_env_file=None)
    assert config.DISCORD_BOT_TOKEN == "test-token"
    assert config.BOT_USER_ID == "1234567890"
    assert config.DB_NAME == "/tmp/test.sqlite"
    assert config.OPENROUTER_API_KEY == "sk-or-test"
    assert config.OPENROUTER_MODEL == "test/model"
    assert config.OLLAMA_MODEL == "gemma3:4b"  # default fallback model


def test_config_defaults(mocker: MockerFixture):
    mocker.patch.dict(os.environ, REQUIRED_ENV, clear=True)
    config = Config(_env_file=None)
    assert config.DISCORD_MAX_MESSAGE_LENGTH == 2000
    assert config.MEETUP_EVENT_COUNT == 100
    assert config.HANDBOOK_TOKEN_BUDGET == 100000
    assert config.DISCORD_CONTENT_TOKEN_BUDGET == 100000
    assert config.CHAIN_TOKEN_BUDGET == 10000
    assert config.LLM_NUM_CTX == 131072
    assert "wiki.capefearmakersguild.org" in config.HANDBOOK_URLS


def test_config_missing_required_var(mocker: MockerFixture):
    incomplete = dict(REQUIRED_ENV)
    del incomplete["OPENROUTER_API_KEY"]
    mocker.patch.dict(os.environ, incomplete, clear=True)
    with pytest.raises(ValidationError):
        Config(_env_file=None)


def test_config_extra_keys_ignored(mocker: MockerFixture):
    env = {**REQUIRED_ENV, "TOTALLY_UNKNOWN_KEY": "xxx"}
    mocker.patch.dict(os.environ, env, clear=True)
    config = Config(_env_file=None)
    assert not hasattr(config, "TOTALLY_UNKNOWN_KEY")
