import http.client
import json
import time
from typing import Callable, Literal
from urllib.parse import urlsplit

from openparl_extractor.block_classification import FrozenModel, unique_object
from openparl_extractor.config import LlmConfig


MAX_RESPONSE_BYTES = 1_048_576


class HttpResult(FrozenModel):
    status: int | None = None
    raw_response: str | None = None
    content: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    error_kind: Literal["structure_error", "transport_error"] | None = None
    error: str | None = None
    latency_seconds: float


def completion_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base URL requires HTTPS without credentials, query or fragment")
    return base_url.rstrip("/") + "/chat/completions"


def decode_completion(raw: str) -> dict[str, object]:
    body = json.loads(raw, object_pairs_hook=unique_object)
    choices = body["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("expected exactly one completion choice")
    choice = choices[0]
    if choice["finish_reason"] != "stop" or not isinstance(choice["message"]["content"], str):
        raise ValueError("expected stop finish and string message content")
    usage = body.get("usage")
    if usage is not None:
        keys = ("prompt_tokens", "completion_tokens", "total_tokens")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in keys):
            raise ValueError("invalid provider usage")
        usage = {k: usage[k] for k in keys}
    return {"content": choice["message"]["content"], "finish_reason": "stop", "usage": usage}


def response_metadata(raw: str) -> dict[str, object]:
    try:
        body = json.loads(raw, object_pairs_hook=unique_object)
        choice = body.get("choices", [{}])[0]
        return {"finish_reason": choice.get("finish_reason"), "usage": body.get("usage")}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return {}


class CategoryHttpClient:
    def __init__(
        self, config: LlmConfig,
        connection_factory: Callable[..., http.client.HTTPSConnection] = http.client.HTTPSConnection,
    ) -> None:
        self.config = config
        self.endpoint = completion_endpoint(str(config.base_url))
        self.connection_factory = connection_factory

    def post(self, body: bytes, timeout: int) -> HttpResult:
        start = time.monotonic()
        parsed = urlsplit(self.endpoint)
        connection = None
        try:
            connection = self.connection_factory(parsed.hostname, port=parsed.port, timeout=timeout)
            return self._exchange(connection, parsed.path, body, start)
        except (OSError, http.client.HTTPException) as error:
            return HttpResult(
                error_kind="transport_error", error=type(error).__name__,
                latency_seconds=time.monotonic() - start,
            )
        finally:
            if connection:
                connection.close()

    def _exchange(self, connection, path: str, body: bytes, start: float) -> HttpResult:
        connection.request("POST", path, body=body, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.config.api_key.get_secret_value(),
        })
        response = connection.getresponse()
        raw_bytes = response.read(MAX_RESPONSE_BYTES + 1)
        raw = raw_bytes.decode("utf-8", errors="replace")
        raw = raw.replace(self.config.api_key.get_secret_value(), "[REDACTED_CREDENTIAL]")
        elapsed = time.monotonic() - start
        metadata = response_metadata(raw)
        if len(raw_bytes) > MAX_RESPONSE_BYTES or not 200 <= response.status < 300:
            return HttpResult(status=response.status, raw_response=raw, latency_seconds=elapsed,
                              error_kind="transport_error", error="HTTP error or response size limit",
                              **self._safe_metadata(metadata))
        return self._decode(response.status, raw, metadata, elapsed, raw_bytes)

    def _decode(self, status: int, raw: str, metadata: dict, elapsed: float, raw_bytes: bytes) -> HttpResult:
        try:
            raw_bytes.decode("utf-8")
            value = decode_completion(raw)
        except (ValueError, KeyError, TypeError, IndexError):
            return HttpResult(status=status, raw_response=raw, latency_seconds=elapsed,
                              error_kind="structure_error", error="invalid completion envelope",
                              **self._safe_metadata(metadata))
        return HttpResult(status=status, raw_response=raw, latency_seconds=elapsed, **value)

    def _safe_metadata(self, metadata: dict) -> dict[str, object]:
        finish = metadata.get("finish_reason")
        usage = metadata.get("usage")
        keys = ("prompt_tokens", "completion_tokens", "total_tokens")
        valid = isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in keys)
        return {"finish_reason": finish if isinstance(finish, str) else None,
                "usage": {k: usage[k] for k in keys} if valid else None}
