import pytest

from openparl_extractor.config import ConfigError, load_llm_config


def test_loads_valid_llm_config() -> None:
    config = load_llm_config(
        {
            "LLM_NAME": "swiss-ai/Apertus-v1.5-8B",
            "LLM_BASE_URL": "https://apertus.example/v1",
            "LLM_API_KEY": "secret",
        }
    )

    assert config.name == "swiss-ai/Apertus-v1.5-8B"
    assert str(config.base_url) == "https://apertus.example/v1"
    assert config.api_key.get_secret_value() == "secret"


def test_rejects_missing_llm_config() -> None:
    with pytest.raises(ConfigError):
        load_llm_config({})
