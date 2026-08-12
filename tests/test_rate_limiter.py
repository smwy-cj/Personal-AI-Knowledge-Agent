import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.cancellation import CancellationToken, OperationCancelled
from personal_ai_agent.rate_limiter import (
    ProviderRateLimitExceeded,
    SQLiteProviderRateLimiter,
)


class MutableClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


class ProviderRateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "limits.sqlite3"
        self.clock = MutableClock()

    def tearDown(self):
        self.temporary.cleanup()

    def limiter(self, sleeper=lambda seconds: None):
        return SQLiteProviderRateLimiter(
            self.database, clock=self.clock, sleeper=sleeper
        )

    def test_two_instances_share_smooth_slots(self):
        first = self.limiter()
        second = self.limiter()

        self.assertEqual(first.reserve("provider", 60, 10), 0.0)
        self.assertEqual(second.reserve("provider", 60, 10), 1.0)
        self.clock.value += 0.25
        self.assertEqual(first.reserve("provider", 60, 10), 1.75)

    def test_excessive_wait_is_rejected_without_consuming_a_slot(self):
        limiter = self.limiter()
        limiter.reserve("provider", 60, 10)

        with self.assertRaises(ProviderRateLimitExceeded):
            limiter.reserve("provider", 60, 0.5)

        self.clock.value += 1.0
        self.assertEqual(limiter.reserve("provider", 60, 0.0), 0.0)

    def test_wait_uses_injected_sleeper_and_can_be_cancelled(self):
        delays = []
        limiter = self.limiter(delays.append)
        limiter.wait("provider", 60, 10)
        limiter.wait("provider", 60, 10)
        self.assertEqual(delays, [1.0])

        token = CancellationToken()
        token.cancel()
        with self.assertRaises(OperationCancelled):
            limiter.wait("another", 60, 10, token)

    def test_token_reservations_are_shared_and_weighted(self):
        first = self.limiter()
        second = self.limiter()

        self.assertEqual(first.reserve_tokens("provider", 60, 10, 20), 0.0)
        self.assertEqual(second.reserve_tokens("provider", 60, 5, 20), 10.0)
        self.clock.value += 4.0
        self.assertEqual(first.reserve_tokens("provider", 60, 1, 20), 11.0)

    def test_oversized_token_reservation_does_not_consume_quota(self):
        limiter = self.limiter()

        with self.assertRaises(ProviderRateLimitExceeded):
            limiter.reserve_tokens("provider", 100, 101, 30)

        self.assertEqual(limiter.reserve_tokens("provider", 100, 1, 0), 0.0)

    def test_request_and_token_capacity_wait_once_for_the_larger_delay(self):
        delays = []
        limiter = self.limiter(delays.append)

        self.assertEqual(limiter.reserve_capacity("provider", 60, 60, 10, 20), 0.0)
        self.assertEqual(
            limiter.wait_for_capacity("provider", 60, 60, 5, 20), 10.0
        )
        self.assertEqual(delays, [10.0])

    def test_provider_cooldown_is_shared_and_never_shortened(self):
        first = self.limiter()
        second = self.limiter()

        self.assertEqual(first.defer_provider("provider", 5), 5.0)
        self.assertEqual(second.defer_provider("provider", 2), 5.0)
        self.assertEqual(second.reserve("provider", 60, 10), 5.0)

    def test_network_admission_rechecks_cooldown_without_concurrency_limit(self):
        limiter = self.limiter()
        limiter.defer_provider("provider", 5)

        with self.assertRaises(ProviderRateLimitExceeded):
            with limiter.concurrency_slot("provider", None, 0, 30):
                pass

    def test_actual_token_usage_reconciles_estimate_idempotently(self):
        limiter = self.limiter()
        reservation = limiter.reserve_capacity_tracked(
            "provider", 600, 60, 10, 20
        )

        self.assertEqual(limiter.reconcile_tokens(reservation, 4), -6)
        self.assertEqual(limiter.reconcile_tokens(reservation, 4), -6)
        self.assertEqual(limiter.reserve_tokens("provider", 60, 1, 20), 4.0)
        with self.assertRaises(ValueError):
            limiter.reconcile_tokens(reservation, 5)

    def test_underestimate_adds_tokens_and_late_refund_stays_conservative(self):
        limiter = self.limiter()
        underestimated = limiter.reserve_capacity_tracked(
            "under", 600, 60, 5, 20
        )
        self.assertEqual(limiter.reconcile_tokens(underestimated, 8), 3)
        self.assertEqual(limiter.reserve_tokens("under", 60, 1, 20), 8.0)

        first = limiter.reserve_capacity_tracked("queued", 600, 60, 10, 20)
        limiter.reserve_capacity_tracked("queued", 600, 60, 5, 20)
        self.assertEqual(limiter.reconcile_tokens(first, 4), 0)
        self.assertEqual(limiter.reserve_tokens("queued", 60, 1, 20), 15.0)

    def test_concurrency_slots_are_shared_and_released(self):
        first = self.limiter()
        second = self.limiter()

        with first.concurrency_slot("provider", 1, 0, 30):
            with self.assertRaises(ProviderRateLimitExceeded):
                with second.concurrency_slot("provider", 1, 0, 30):
                    pass

        with second.concurrency_slot("provider", 1, 0, 30):
            pass

    def test_expired_concurrency_lease_is_recovered(self):
        first = self.limiter()
        second = self.limiter()
        stale = first.concurrency_slot("provider", 1, 0, 5)
        stale.__enter__()
        try:
            self.clock.value += 5.0
            with second.concurrency_slot("provider", 1, 0, 5):
                pass
        finally:
            stale.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
