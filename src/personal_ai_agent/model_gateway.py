"""Capability-based model routing with bounded retry, fallback and trace."""

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Protocol, Sequence

from .models import ModelCallRecord
from .cancellation import CancellationToken, check_cancelled
from .observability import record_event_safely


SchemaValidator = Callable[[Dict[str, Any]], None]


class ModelGatewayError(ValueError):
    """A terminal gateway error; orchestration must not retry it again."""


class ModelCapabilityError(ModelGatewayError):
    pass


class ModelCallBudgetExceeded(ModelGatewayError):
    pass


class RetryableModelError(ModelGatewayError):
    """Providers raise this only for failures that are safe to retry/fallback."""

    def __init__(
        self, message: str, retry_after_seconds: Optional[float] = None
    ) -> None:
        super().__init__(message)
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")
        self.retry_after_seconds = retry_after_seconds


class StructuredOutputError(ModelGatewayError):
    pass


class CostLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class PrivacyLevel(IntEnum):
    PUBLIC = 1
    PERSONAL = 2
    SENSITIVE = 3


@dataclass(frozen=True)
class ModelRequest:
    task_type: str
    prompt_version: str
    payload: Dict[str, Any]
    required_capabilities: FrozenSet[str] = frozenset({"structured_output"})
    timeout_seconds: float = 30.0
    max_output_tokens: int = 2_000
    estimated_input_tokens: int = 0
    max_cost_level: CostLevel = CostLevel.HIGH
    privacy_level: PrivacyLevel = PrivacyLevel.PERSONAL
    schema_name: str = "unspecified"
    cancellation_token: Optional[CancellationToken] = None
    task_id: Optional[str] = None
    step_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.task_type.strip() or not self.prompt_version.strip():
            raise ValueError("task_type and prompt_version must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("model timeout must be positive")
        if self.max_output_tokens <= 0 or self.estimated_input_tokens < 0:
            raise ValueError("model token limits are invalid")


@dataclass(frozen=True)
class ProviderResponse:
    data: Dict[str, Any]
    model_id: str
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("model token usage must be non-negative")


@dataclass(frozen=True)
class GatewayResponse:
    data: Dict[str, Any]
    trace: ModelCallRecord
    model_call_count: int


class ModelProvider(Protocol):
    @property
    def provider_id(self) -> str:
        ...

    def generate(self, request: ModelRequest) -> ProviderResponse:
        """Generate within request.timeout_seconds or raise an error."""
        ...


@dataclass(frozen=True)
class ModelProfile:
    provider: ModelProvider
    capabilities: FrozenSet[str]
    max_context_tokens: int
    cost_level: CostLevel
    max_privacy_level: PrivacyLevel
    priority: int = 100
    input_cost_per_million_tokens_usd: float = 0.0
    output_cost_per_million_tokens_usd: float = 0.0

    def __post_init__(self) -> None:
        if not self.provider.provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")
        if (
            self.input_cost_per_million_tokens_usd < 0
            or self.output_cost_per_million_tokens_usd < 0
        ):
            raise ValueError("model token prices must be non-negative")


class ModelCapabilityRegistry:
    def __init__(self, profiles: Sequence[ModelProfile]) -> None:
        if not profiles:
            raise ValueError("at least one model profile is required")
        provider_ids = [profile.provider.provider_id for profile in profiles]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("model provider ids must be unique")
        self.profiles = list(profiles)

    @classmethod
    def from_providers(cls, providers: Sequence[Any]) -> "ModelCapabilityRegistry":
        """Compatibility helper for simple providers from Iteration 6."""
        return cls(
            [
                ModelProfile(
                    provider=provider,
                    capabilities=provider.capabilities,
                    max_context_tokens=1_000_000,
                    cost_level=CostLevel.MEDIUM,
                    max_privacy_level=PrivacyLevel.PERSONAL,
                    priority=index,
                )
                for index, provider in enumerate(providers)
            ]
        )

    def route(
        self, request: ModelRequest, provider_id: Optional[str] = None
    ) -> List[ModelProfile]:
        required_context = request.estimated_input_tokens + request.max_output_tokens
        candidates = []
        for order, profile in enumerate(self.profiles):
            if provider_id is not None and profile.provider.provider_id != provider_id:
                continue
            if not request.required_capabilities <= profile.capabilities:
                continue
            if required_context > profile.max_context_tokens:
                continue
            if profile.cost_level > request.max_cost_level:
                continue
            if request.privacy_level > profile.max_privacy_level:
                continue
            candidates.append((profile.cost_level, profile.priority, order, profile))
        if not candidates:
            target = " provider %s" % provider_id if provider_id else ""
            raise ModelCapabilityError(
                "no%s satisfies capability, context, cost and privacy constraints" % target
            )
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in candidates]


class ModelGateway:
    def __init__(
        self,
        providers: Optional[Sequence[ModelProvider]] = None,
        max_retries: int = 1,
        registry: Optional[ModelCapabilityRegistry] = None,
        retry_base_seconds: float = 0.25,
        max_retry_delay_seconds: float = 8.0,
        sleeper: Callable[[float], None] = time.sleep,
        event_store: Optional[Any] = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if registry is not None and providers is not None:
            raise ValueError("provide either providers or registry, not both")
        if retry_base_seconds < 0 or max_retry_delay_seconds < 0:
            raise ValueError("retry delays must be non-negative")
        if registry is None:
            if not providers:
                raise ValueError("at least one model provider is required")
            registry = ModelCapabilityRegistry.from_providers(providers)
        self.registry = registry
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.max_retry_delay_seconds = max_retry_delay_seconds
        self.sleeper = sleeper
        self.event_store = event_store

    def generate(
        self,
        request: ModelRequest,
        validator: SchemaValidator,
        provider_id: Optional[str] = None,
        max_model_calls: Optional[int] = None,
    ) -> GatewayResponse:
        if max_model_calls is not None and max_model_calls <= 0:
            raise ModelCallBudgetExceeded("model call budget exhausted")
        profiles = self.registry.route(request, provider_id)
        if provider_id is not None:
            profiles = profiles[:1]
        started = time.monotonic()
        total_attempts = 0
        attempted_provider_ids: List[str] = []
        last_error: Optional[RetryableModelError] = None
        pending_delay: Optional[float] = None

        for profile in profiles:
            provider_attempts = 0
            while provider_attempts <= self.max_retries:
                check_cancelled(request.cancellation_token)
                if max_model_calls is not None and total_attempts >= max_model_calls:
                    raise ModelCallBudgetExceeded("model call budget exhausted during fallback")
                if pending_delay is not None:
                    self._wait(pending_delay, request.cancellation_token)
                    pending_delay = None
                provider_attempts += 1
                total_attempts += 1
                attempted_provider_ids.append(profile.provider.provider_id)
                self._observe(
                    "model_attempt",
                    request,
                    {
                        "provider_id": profile.provider.provider_id,
                        "task_type": request.task_type,
                        "prompt_version": request.prompt_version,
                        "attempt": total_attempts,
                    },
                )
                try:
                    response = profile.provider.generate(request)
                    if not isinstance(response.data, dict):
                        raise StructuredOutputError("model response data must be an object")
                    try:
                        validator(response.data)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise StructuredOutputError(
                            "response does not satisfy %s: %s" % (request.schema_name, exc)
                        ) from exc
                    latency_ms = int((time.monotonic() - started) * 1000)
                    trace = ModelCallRecord(
                        provider_id=profile.provider.provider_id,
                        model_id=response.model_id,
                        task_type=request.task_type,
                        prompt_version=request.prompt_version,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        latency_ms=latency_ms,
                        attempt_count=total_attempts,
                        attempted_provider_ids=attempted_provider_ids,
                    )
                    self._observe(
                        "model_completed",
                        request,
                        {
                            "provider_id": profile.provider.provider_id,
                            "model_id": response.model_id,
                            "task_type": request.task_type,
                            "prompt_version": request.prompt_version,
                            "input_tokens": response.input_tokens,
                            "output_tokens": response.output_tokens,
                            "duration_ms": latency_ms,
                            "model_call_count": total_attempts,
                            "estimated_cost_microusd": int(
                                round(
                                    response.input_tokens
                                    * profile.input_cost_per_million_tokens_usd
                                    + response.output_tokens
                                    * profile.output_cost_per_million_tokens_usd
                                )
                            ),
                        },
                    )
                    return GatewayResponse(response.data, trace, total_attempts)
                except RetryableModelError as exc:
                    last_error = exc
                    pending_delay = self._retry_delay(exc, total_attempts)
                    self._observe(
                        "model_retry",
                        request,
                        {
                            "provider_id": profile.provider.provider_id,
                            "task_type": request.task_type,
                            "prompt_version": request.prompt_version,
                            "attempt": total_attempts,
                            "retry_delay_ms": int(pending_delay * 1000),
                            "error_type": type(exc).__name__,
                        },
                    )
                    if provider_attempts <= self.max_retries:
                        continue
                    break
        if last_error is not None:
            raise RetryableModelError(
                "all routed model providers failed after %s calls: %s"
                % (total_attempts, last_error)
            ) from last_error
        raise ModelCapabilityError("no model provider was executed")

    def _retry_delay(self, error: RetryableModelError, attempt: int) -> float:
        requested = error.retry_after_seconds
        if requested is None:
            requested = self.retry_base_seconds * (2 ** max(0, attempt - 1))
        return min(requested, self.max_retry_delay_seconds)

    def _wait(
        self, delay_seconds: float, token: Optional[CancellationToken]
    ) -> None:
        if delay_seconds <= 0:
            check_cancelled(token)
        elif token is not None:
            token.wait(delay_seconds)
        else:
            self.sleeper(delay_seconds)

    def _observe(
        self, event_type: str, request: ModelRequest, attributes: Dict[str, Any]
    ) -> None:
        if self.event_store is not None:
            record_event_safely(
                self.event_store,
                event_type,
                task_id=request.task_id,
                step_id=request.step_id,
                attributes=attributes,
            )
