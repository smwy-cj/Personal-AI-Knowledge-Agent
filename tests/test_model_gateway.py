import tempfile
import unittest
from pathlib import Path
from typing import FrozenSet

from personal_ai_agent.cancellation import CancellationToken, OperationCancelled
from personal_ai_agent.model_gateway import (
    ModelCapabilityError,
    ModelGateway,
    ModelCapabilityRegistry,
    ModelProfile,
    ModelRequest,
    CostLevel,
    PrivacyLevel,
    ProviderResponse,
    RetryableModelError,
    StructuredOutputError,
)
from personal_ai_agent.observability import SQLiteEventStore


class FakeProvider:
    provider_id = "fake-provider"
    capabilities: FrozenSet[str] = frozenset({"structured_output", "chinese"})

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ModelGatewayTests(unittest.TestCase):
    def test_retries_only_retryable_errors_and_records_trace(self):
        provider = FakeProvider(
            [
                RetryableModelError("busy"),
                ProviderResponse({"value": "ok"}, "model-v1", 12, 4),
            ]
        )
        gateway = ModelGateway([provider], max_retries=1)
        result = gateway.generate(
            ModelRequest("test", "prompt-v1", {}, schema_name="value_v1"),
            lambda data: None if data.get("value") == "ok" else (_ for _ in ()).throw(ValueError()),
        )

        self.assertEqual(2, provider.calls)
        self.assertEqual(2, result.trace.attempt_count)
        self.assertEqual(16, result.trace.input_tokens + result.trace.output_tokens)

    def test_records_estimated_cost_from_actual_usage_and_profile_prices(self):
        provider = FakeProvider(
            [ProviderResponse({"value": "ok"}, "model-v1", 12, 4)]
        )
        profile = ModelProfile(
            provider=provider,
            capabilities=provider.capabilities,
            max_context_tokens=8192,
            cost_level=CostLevel.MEDIUM,
            max_privacy_level=PrivacyLevel.PERSONAL,
            input_cost_per_million_tokens_usd=2.0,
            output_cost_per_million_tokens_usd=8.0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = SQLiteEventStore(Path(temporary) / "events.sqlite3")
            ModelGateway(
                registry=ModelCapabilityRegistry([profile]), event_store=store
            ).generate(
                ModelRequest("test", "v1", {}), lambda data: None
            )

            completed = store.list_events("model_completed")[0]

        self.assertEqual(completed.attributes["estimated_cost_microusd"], 56)

    def test_schema_failure_is_not_retried(self):
        provider = FakeProvider([ProviderResponse({}, "model-v1", 1, 1)])
        with self.assertRaises(StructuredOutputError):
            ModelGateway([provider], max_retries=2).generate(
                ModelRequest("test", "v1", {}, schema_name="required"),
                lambda data: (_ for _ in ()).throw(ValueError("missing")),
            )
        self.assertEqual(1, provider.calls)

    def test_exhausted_gateway_retry_is_a_terminal_value_error(self):
        provider = FakeProvider(
            [RetryableModelError("busy"), RetryableModelError("still busy")]
        )
        with self.assertRaises(ValueError):
            ModelGateway([provider], max_retries=1).generate(
                ModelRequest("test", "v1", {}), lambda data: None
            )
        self.assertEqual(2, provider.calls)

    def test_capability_mismatch_fails_before_provider_call(self):
        provider = FakeProvider([])
        request = ModelRequest(
            "test", "v1", {}, required_capabilities=frozenset({"vision"})
        )
        with self.assertRaises(ModelCapabilityError):
            ModelGateway([provider]).generate(request, lambda data: None)
        self.assertEqual(0, provider.calls)

    def test_exponential_backoff_is_bounded_and_injectable(self):
        provider = FakeProvider(
            [
                RetryableModelError("busy"),
                RetryableModelError("still busy"),
                ProviderResponse({"value": "ok"}, "model-v1", 1, 1),
            ]
        )
        delays = []
        gateway = ModelGateway(
            [provider],
            max_retries=2,
            retry_base_seconds=1.0,
            max_retry_delay_seconds=1.5,
            sleeper=delays.append,
        )

        gateway.generate(
            ModelRequest("test", "v1", {}), lambda data: None
        )

        self.assertEqual(delays, [1.0, 1.5])

    def test_retry_after_takes_priority_but_is_capped(self):
        provider = FakeProvider(
            [
                RetryableModelError("rate limited", retry_after_seconds=20.0),
                ProviderResponse({"value": "ok"}, "model-v1", 1, 1),
            ]
        )
        delays = []
        ModelGateway(
            [provider],
            max_retries=1,
            retry_base_seconds=1.0,
            max_retry_delay_seconds=3.0,
            sleeper=delays.append,
        ).generate(ModelRequest("test", "v1", {}), lambda data: None)
        self.assertEqual(delays, [3.0])

    def test_cancelled_request_stops_before_provider_call(self):
        token = CancellationToken()
        token.cancel()
        provider = FakeProvider(
            [ProviderResponse({"value": "ok"}, "model-v1", 1, 1)]
        )
        with self.assertRaises(OperationCancelled):
            ModelGateway([provider]).generate(
                ModelRequest("test", "v1", {}, cancellation_token=token),
                lambda data: None,
            )
        self.assertEqual(provider.calls, 0)

    def test_cancellation_interrupts_retry_wait(self):
        token = CancellationToken()
        provider = FakeProvider(
            [
                RetryableModelError("busy"),
                ProviderResponse({"value": "ok"}, "model-v1", 1, 1),
            ]
        )
        gateway = ModelGateway([provider], max_retries=1, retry_base_seconds=30.0)
        original_wait = token.wait

        def cancel_during_wait(seconds):
            token.cancel()
            original_wait(0)

        token.wait = cancel_during_wait
        with self.assertRaises(OperationCancelled):
            gateway.generate(
                ModelRequest("test", "v1", {}, cancellation_token=token),
                lambda data: None,
            )
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
