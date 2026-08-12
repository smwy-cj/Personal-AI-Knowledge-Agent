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


if __name__ == "__main__":
    unittest.main()
