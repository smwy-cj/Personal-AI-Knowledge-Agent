"""Cooperative cancellation boundary shared by gateways and adapters."""

from threading import Event
from typing import Callable, Optional


class OperationCancelled(ValueError):
    pass


class CancellationToken:
    def __init__(
        self, external_check: Optional[Callable[[], bool]] = None
    ) -> None:
        self._event = Event()
        self._external_check = external_check

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set() or bool(
            self._external_check is not None and self._external_check()
        )

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise OperationCancelled("operation was cancelled")

    def wait(self, timeout_seconds: float) -> None:
        if timeout_seconds < 0:
            raise ValueError("cancellation wait must be non-negative")
        if self._external_check is None:
            if self._event.wait(timeout_seconds):
                raise OperationCancelled("operation was cancelled")
            return
        remaining = timeout_seconds
        while remaining > 0:
            interval = min(0.1, remaining)
            if self._event.wait(interval):
                raise OperationCancelled("operation was cancelled")
            self.raise_if_cancelled()
            remaining -= interval
        self.raise_if_cancelled()


def check_cancelled(token: Optional[CancellationToken]) -> None:
    if token is not None:
        token.raise_if_cancelled()
