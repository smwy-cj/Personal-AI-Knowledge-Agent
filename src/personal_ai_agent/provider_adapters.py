"""Standard-library adapters for OpenAI-compatible JSON HTTP endpoints."""

import json
import os
import re
import time
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


class _ProviderJsonDocument(dict):
    def __init__(
        self,
        document: Dict[str, Any],
        rate_limit_reset_seconds: Optional[float],
    ) -> None:
        super().__init__(document)
        self.rate_limit_reset_seconds = rate_limit_reset_seconds


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
        reservation = None
        if self.rate_limiter is not None:
            reservation = self.rate_limiter.wait_for_capacity_tracked(
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
                max(
                    0.0,
                    self.config.max_rate_limit_wait_seconds - reservation.delay,
                ),
                max(
                    self.config.concurrency_lease_seconds,
                    request.timeout_seconds + 5.0,
                ),
                request.cancellation_token,
            )
        else:
            concurrency = _unlimited_concurrency()
        try:
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
        except RetryableModelError as exc:
            self._apply_retry_after(exc)
            raise
        self._apply_response_cooldown(document)
        usage = document.get("usage") or {}
        actual_tokens = _complete_model_usage(usage)
        if (
            self.rate_limiter is not None
            and reservation is not None
            and actual_tokens is not None
        ):
            self.rate_limiter.reconcile_tokens(reservation, actual_tokens)
        try:
            content = document["choices"][0]["message"]["content"]
            data = content if isinstance(content, dict) else json.loads(content)
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

    def _apply_retry_after(self, error: RetryableModelError) -> None:
        if self.rate_limiter is not None and error.retry_after_seconds is not None:
            self.rate_limiter.defer_provider(
                self.provider_id, error.retry_after_seconds
            )

    def _apply_response_cooldown(self, document: Dict[str, Any]) -> None:
        cooldown = getattr(document, "rate_limit_reset_seconds", None)
        if self.rate_limiter is not None and cooldown is not None:
            self.rate_limiter.defer_provider(self.provider_id, cooldown)


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
        reservation = None
        try:
            if self.rate_limiter is not None:
                reservation = self.rate_limiter.wait_for_capacity_tracked(
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
                    max(
                        0.0,
                        self.config.max_rate_limit_wait_seconds - reservation.delay,
                    ),
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
        except RetryableModelError as exc:
            if self.rate_limiter is not None and exc.retry_after_seconds is not None:
                self.rate_limiter.defer_provider(
                    self.provider_id, exc.retry_after_seconds
                )
            raise
        except ProviderPayloadTooLarge:
            if len(texts) == 1:
                raise ProviderPayloadTooLarge(
                    "one embedding input exceeds the provider payload limit"
                )
            midpoint = len(texts) // 2
            return self._embed_batch(texts[:midpoint]) + self._embed_batch(
                texts[midpoint:]
            )
        cooldown = getattr(document, "rate_limit_reset_seconds", None)
        if self.rate_limiter is not None and cooldown is not None:
            self.rate_limiter.defer_provider(self.provider_id, cooldown)
        usage = document.get("usage") or {}
        actual_tokens = _complete_embedding_usage(usage)
        if (
            self.rate_limiter is not None
            and reservation is not None
            and actual_tokens is not None
        ):
            self.rate_limiter.reconcile_tokens(reservation, actual_tokens)
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
            response_cooldown = _rate_limit_reset_seconds(
                getattr(response, "headers", None)
            )
    except HTTPError as exc:
        if exc.code == 413:
            raise ProviderPayloadTooLarge("provider rejected the request payload size") from exc
        if exc.code == 429 or exc.code >= 500:
            retry_after = _retry_after_seconds(
                exc.headers.get("Retry-After") if exc.headers is not None else None
            )
            if retry_after is None:
                retry_after = _rate_limit_reset_seconds(exc.headers)
            raise RetryableModelError(
                "provider temporarily unavailable (HTTP %s)" % exc.code,
                retry_after,
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
    return _ProviderJsonDocument(document, response_cooldown)


@contextmanager
def _unlimited_concurrency() -> Iterator[None]:
    yield


def _usage_integer(usage: Dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _complete_model_usage(usage: Any) -> Optional[int]:
    if not isinstance(usage, dict):
        return None
    total = _optional_usage_integer(usage, "total_tokens")
    if total is not None:
        return total
    prompt = _optional_usage_integer(usage, "prompt_tokens")
    completion = _optional_usage_integer(usage, "completion_tokens")
    return prompt + completion if prompt is not None and completion is not None else None


def _complete_embedding_usage(usage: Any) -> Optional[int]:
    if not isinstance(usage, dict):
        return None
    total = _optional_usage_integer(usage, "total_tokens")
    if total is not None:
        return total
    return _optional_usage_integer(usage, "prompt_tokens")


def _optional_usage_integer(usage: Dict[str, Any], key: str) -> Optional[int]:
    value = usage.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


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


def _rate_limit_reset_seconds(headers: Any) -> Optional[float]:
    if headers is None:
        return None
    retry_after = _retry_after_seconds(headers.get("Retry-After"))
    delays = [retry_after] if retry_after is not None else []
    for remaining_name, reset_name in (
        ("X-RateLimit-Remaining-Requests", "X-RateLimit-Reset-Requests"),
        ("X-RateLimit-Remaining-Tokens", "X-RateLimit-Reset-Tokens"),
        ("RateLimit-Remaining", "RateLimit-Reset"),
    ):
        remaining = _non_negative_number(headers.get(remaining_name))
        if remaining == 0:
            reset = _reset_delay_seconds(headers.get(reset_name))
            if reset is not None:
                delays.append(reset)
    return max(delays) if delays else None


def _non_negative_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 0 and number != float("inf") else None


def _reset_delay_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().casefold()
    numeric = _non_negative_number(text)
    if numeric is not None:
        return max(0.0, numeric - time.time()) if numeric > 10_000_000 else numeric
    matches = list(re.finditer(r"(\d+(?:\.\d+)?)(ms|s|m|h)", text))
    if not matches or "".join(match.group(0) for match in matches) != text:
        return None
    factors = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(match.group(1)) * factors[match.group(2)] for match in matches)
