import unittest
from typing import FrozenSet

from personal_ai_agent.model_gateway import (
    CostLevel,
    ModelCallBudgetExceeded,
    ModelCapabilityError,
    ModelCapabilityRegistry,
    ModelGateway,
    ModelProfile,
    ModelRequest,
    PrivacyLevel,
    ProviderResponse,
    RetryableModelError,
)


class RoutedProvider:
    def __init__(self, provider_id, responses):
        self.provider_id = provider_id
        self.responses = list(responses)
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def profile(provider, capabilities, context, cost, privacy, priority=100):
    return ModelProfile(
        provider,
        frozenset(capabilities),
        context,
        cost,
        privacy,
        priority,
    )


class ModelRoutingTests(unittest.TestCase):
    def test_routes_by_capability_context_cost_and_privacy(self):
        cloud = RoutedProvider("cloud-cheap", [ProviderResponse({"ok": 1}, "m1", 1, 1)])
        local = RoutedProvider("local-private", [ProviderResponse({"ok": 1}, "m2", 1, 1)])
        registry = ModelCapabilityRegistry(
            [
                profile(cloud, ["structured_output"], 10_000, CostLevel.LOW, PrivacyLevel.PUBLIC),
                profile(local, ["structured_output"], 10_000, CostLevel.MEDIUM, PrivacyLevel.SENSITIVE),
            ]
        )
        request = ModelRequest(
            "summary",
            "v1",
            {},
            privacy_level=PrivacyLevel.SENSITIVE,
            max_cost_level=CostLevel.MEDIUM,
        )
        result = ModelGateway(registry=registry).generate(request, lambda data: None)
        self.assertEqual("local-private", result.trace.provider_id)
        self.assertEqual(0, cloud.calls)

    def test_fallback_after_retryable_failure_records_route(self):
        primary = RoutedProvider("primary", [RetryableModelError("down")])
        fallback = RoutedProvider("fallback", [ProviderResponse({"ok": 1}, "m2", 3, 2)])
        registry = ModelCapabilityRegistry(
            [
                profile(primary, ["structured_output"], 10_000, CostLevel.LOW, PrivacyLevel.PERSONAL),
                profile(fallback, ["structured_output"], 10_000, CostLevel.MEDIUM, PrivacyLevel.PERSONAL),
            ]
        )
        result = ModelGateway(registry=registry, max_retries=0).generate(
            ModelRequest("summary", "v1", {}), lambda data: None
        )
        self.assertEqual("fallback", result.trace.provider_id)
        self.assertEqual(["primary", "fallback"], result.trace.attempted_provider_ids)
        self.assertEqual(2, result.model_call_count)

    def test_budget_stops_fallback_before_second_provider(self):
        primary = RoutedProvider("primary", [RetryableModelError("down")])
        fallback = RoutedProvider("fallback", [ProviderResponse({"ok": 1}, "m2", 1, 1)])
        registry = ModelCapabilityRegistry(
            [
                profile(primary, ["structured_output"], 10_000, CostLevel.LOW, PrivacyLevel.PERSONAL),
                profile(fallback, ["structured_output"], 10_000, CostLevel.MEDIUM, PrivacyLevel.PERSONAL),
            ]
        )
        with self.assertRaises(ModelCallBudgetExceeded):
            ModelGateway(registry=registry, max_retries=0).generate(
                ModelRequest("summary", "v1", {}), lambda data: None, max_model_calls=1
            )
        self.assertEqual(0, fallback.calls)

    def test_explicit_provider_does_not_fallback(self):
        primary = RoutedProvider("primary", [RetryableModelError("down")])
        fallback = RoutedProvider("fallback", [ProviderResponse({"ok": 1}, "m2", 1, 1)])
        registry = ModelCapabilityRegistry(
            [
                profile(primary, ["structured_output"], 10_000, CostLevel.LOW, PrivacyLevel.PERSONAL),
                profile(fallback, ["structured_output"], 10_000, CostLevel.LOW, PrivacyLevel.PERSONAL),
            ]
        )
        with self.assertRaises(RetryableModelError):
            ModelGateway(registry=registry, max_retries=0).generate(
                ModelRequest("summary", "v1", {}),
                lambda data: None,
                provider_id="primary",
            )
        self.assertEqual(0, fallback.calls)

    def test_rejects_context_and_cost_mismatch(self):
        provider = RoutedProvider("small", [])
        registry = ModelCapabilityRegistry(
            [profile(provider, ["structured_output"], 100, CostLevel.HIGH, PrivacyLevel.SENSITIVE)]
        )
        request = ModelRequest(
            "summary",
            "v1",
            {},
            estimated_input_tokens=100,
            max_output_tokens=50,
            max_cost_level=CostLevel.MEDIUM,
        )
        with self.assertRaises(ModelCapabilityError):
            ModelGateway(registry=registry).generate(request, lambda data: None)

    def test_unprofiled_provider_is_not_implicitly_authorized_for_sensitive_data(self):
        class LegacyProvider(RoutedProvider):
            capabilities: FrozenSet[str] = frozenset({"structured_output"})

        provider = LegacyProvider(
            "legacy", [ProviderResponse({"ok": 1}, "m1", 1, 1)]
        )
        request = ModelRequest(
            "summary", "v1", {}, privacy_level=PrivacyLevel.SENSITIVE
        )
        with self.assertRaises(ModelCapabilityError):
            ModelGateway([provider]).generate(request, lambda data: None)
        self.assertEqual(0, provider.calls)


if __name__ == "__main__":
    unittest.main()
