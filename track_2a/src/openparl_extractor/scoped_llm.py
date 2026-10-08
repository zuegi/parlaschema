import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable

from openparl_extractor.config import LlmConfig


Transport = Callable[[urllib.request.Request, float], tuple[int, bytes]]
ResponseObserver = Callable[[bytes], None]


class RequestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def http_transport(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (TimeoutError, socket.timeout) as error:
        raise RequestError("timeout", "Model request timed out") from error
    except urllib.error.URLError as error:
        code = "timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "network"
        raise RequestError(code, "Model endpoint unavailable") from error
    except OSError as error:
        raise RequestError("network", "Model connection failed") from error


def complete(config: LlmConfig, body: dict, timeout: float, transport: Transport,
             on_response: ResponseObserver) -> str:
    if not config.name.strip() or not config.api_key.get_secret_value().strip():
        raise RequestError("input", "Model name and API key must be nonblank")
    request = urllib.request.Request(
        str(config.base_url).rstrip("/") + "/chat/completions",
        data=json.dumps({"model": config.name, **body}).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.api_key.get_secret_value()}",
                 "Content-Type": "application/json"}, method="POST",
    )
    status, payload = transport(request, timeout)
    on_response(payload)
    if status != 200:
        raise RequestError("http", f"HTTP {status} from model endpoint")
    return response_content(payload)


def response_content(payload: bytes) -> str:
    try:
        choice = json.loads(payload)["choices"][0]
        content = choice["message"]["content"]
        finish = choice.get("finish_reason")
    except (ValueError, LookupError, TypeError) as error:
        raise RequestError("invalid_output", "Malformed chat completion") from error
    if finish != "stop":
        raise RequestError("invalid_output", "Incomplete model output")
    if not isinstance(content, str) or not content.strip():
        raise RequestError("invalid_output", "Empty model output")
    return content
