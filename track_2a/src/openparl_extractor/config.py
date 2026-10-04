import os
from collections.abc import Mapping

from pydantic import BaseModel, HttpUrl, SecretStr, ValidationError


class ConfigError(Exception):
    pass


class LlmConfig(BaseModel):
    name: str
    base_url: HttpUrl
    api_key: SecretStr


def load_llm_config(environ: Mapping[str, str] = os.environ) -> LlmConfig:
    try:
        return LlmConfig(
            name=environ.get("LLM_NAME", ""),
            base_url=environ.get("LLM_BASE_URL", ""),
            api_key=environ.get("LLM_API_KEY", ""),
        )
    except ValidationError as error:
        raise ConfigError(f"Invalid LLM configuration: {error}") from error
