"""Standard-library adapters for OpenAI-compatible JSON HTTP endpoints."""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterator, List, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import EmbeddingProviderConfig, ModelProviderConfig
from .model_gateway import ModelRequest, ProviderResponse, RetryableModelError
from .rate_limiter import SQLiteProviderRateLimiter


class ProviderConfigurationError(ValueError):
    pass


class ProviderProtocolError(ValueError):
    pass


class ProviderPayloadTooLarge(ProviderProtocolError):
    pass


class OpenAICompatibleModelProvider:
    def __init__(
        self,
        config: ModelProviderConfig,
        rate_limiter: Optional[SQLiteProviderRateLimiter] = None,
    ) -> None:
        self.config = config
        self.provider_id = config.provider_id
        self.rate_limiter = rate_limiter

    def generate(self, request: ModelRequest) -> ProviderResponse:
        if self.rate_limiter is not None:
            quota_delay = self.rate_limiter.wait_for_capacity(
                self.provider_id,
                self.config.requests_per_minute,
                self.config.tokens_per_minute,
                (
                    request.estimated_input_tokens + request.max_output_tokens
                    if self.config.tokens_per_minute is not None
                    else None
                ),
                self.config.max_rate_limit_wait_seconds,
                request.cancellation_token,
            )
            concurrency = self.rate_limiter.concurrency_slot(
                self.provider_id,
                self.config.max_concurrent_requests,
                max(0.0, self.config.max_rate_limit_wait_seconds - quota_delay),
                max(
                    self.config.concurrency_lease_seconds,
                    request.timeout_seconds + 5.0,
                ),
                request.cancellation_token,
            )
        else:
            concurrency = _unlimited_concurrency()
        with concurrency:
            document = _post_json(
                self.config.base_url + "/chat/completions",
                {
                    "model": self.config.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return one JSON object only. Follow the requested schema and "
                                "do not add markdown fences."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(request.payload, ensure_ascii=False),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": request.max_output_tokens,
                },
                self.config.credential_env,
                request.timeout_seconds,
            )
        try:
            content = document["choices"][0]["message"]["content"]
            data = content if isinstance(content, dict) else json.loads(content)
            usage = document.get("usage") or {}
            if not isinstance(data, dict):
                raise TypeError
            return ProviderResponse(
                data=data,
                model_id=str(document.get("model") or self.config.model),
                input_tokens=_usage_integer(usage, "prompt_tokens"),
                output_tokens=_usage_integer(usage, "completion_tokens"),
            )
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderProtocolError(
                "model endpoint returned an invalid structured response"
            ) from exc


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        config: EmbeddingProviderConfig,
        rate_limiter: Optional[SQLiteProviderRateLimiter] = None,
        cancellation_token: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.provider_id = config.provider_id
        self.dimension = config.dimension
        self.rate_limiter = rate_limiter
        self.cancellation_token = cancellation_token

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []
        return self._embed_batch(list(texts))

    def _embed_batch(self, texts: List[str]) -> List[Sequence[float]]:
        try:
            if self.rate_limiter is not None:
                quota_delay = self.rate_limiter.wait_for_capacity(
                    self.provider_id,
                    self.config.requests_per_minute,
                    self.config.tokens_per_minute,
                    (
                        len(texts) * self.config.estimated_tokens_per_input
                        if self.config.tokens_per_minute is not None
                        else None
                    ),
                    self.config.max_rate_limit_wait_seconds,
                    self.cancellation_token,
                )
                concurrency = self.rate_limiter.concurrency_slot(
                    self.provider_id,
                    self.config.max_concurrent_requests,
                    max(0.0, self.config.max_rate_limit_wait_seconds - quota_delay),
                    max(self.config.concurrency_lease_seconds, 35.0),
                    self.cancellation_token,
                )
            else:
                concurrency = _unlimited_concurrency()
            with concurrency:
                document = _post_json(
                    self.config.base_url + "/embeddings",
                    {"model": self.config.model, "input": texts},
                    self.config.credential_env,
                    30.0,
                )
        except ProviderPayloadTooLarge:
            if len(texts) == 1:
                raise ProviderPayloadTooLarge(
                    "one embedding input exceeds the provider payload limit"
                )
            midpoint = len(texts) // 2
            return self._embed_batch(texts[:midpoint]) + self._embed_batch(
                texts[midpoint:]
            )
        try:
            items = sorted(document["data"], key=lambda item: item.get("index", 0))
            vectors: List[Sequence[float]] = [item["embedding"] for item in items]
            if len(vectors) != len(texts):
                raise TypeError
            return vectors
        except (KeyError, TypeError) as exc:
            raise ProviderProtocolError(
                "embedding endpoint returned an invalid response"
            ) from exc


def _post_json(
    url: str,
    payload: Dict[str, Any],
    credential_env: Optional[str],
    timeout_seconds: float,
) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if credential_env:
        credential = os.environ.get(credential_env)
        if not credential:
            raise ProviderConfigurationError(
                "required provider credential environment variable is not set: %s"
                % credential_env
            )
        headers["Authorization"] = "Bearer " + credential
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except HTTPError as exc:
        if exc.code == 413:
            raise ProviderPayloadTooLarge("provider rejected the request payload size") from exc
        if exc.code == 429 or exc.code >= 500:
            raise RetryableModelError(
                "provider temporarily unavailable (HTTP %s)" % exc.code,
                _retry_after_seconds(exc.headers.get("Retry-After")),
            ) from exc
        raise ProviderProtocolError("provider request failed (HTTP %s)" % exc.code) from exc
    except (TimeoutError, URLError) as exc:
        raise RetryableModelError("provider connection failed") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderProtocolError("provider returned invalid JSON") from exc
    if not isinstance(document, dict):
        raise ProviderProtocolError("provider response must be a JSON object")
    return document


@contextmanager
def _unlimited_concurrency() -> Iterator[None]:
    yield


def _usage_integer(usage: Dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip()
    try:
        seconds = float(text)
        return seconds if seconds >= 0 else None
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return max(0.0, (moment - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None
