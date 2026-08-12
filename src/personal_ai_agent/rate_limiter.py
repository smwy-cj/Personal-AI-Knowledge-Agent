"""SQLite-backed smooth provider rate limiting shared across processes."""

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional, Union

from .cancellation import CancellationToken, check_cancelled


class ProviderRateLimitExceeded(ValueError):
    pass


class SQLiteProviderRateLimiter:
    def __init__(
        self,
        database_path: Union[str, Path],
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database_path = str(database_path)
        self.clock = clock
        self.sleeper = sleeper
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_rate_limits (
                    provider_id TEXT PRIMARY KEY,
                    next_slot_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_token_rate_limits (
                    provider_id TEXT PRIMARY KEY,
                    next_slot_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_concurrency_leases (
                    provider_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    lease_until REAL NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(provider_id, lease_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_concurrency_expiry
                ON provider_concurrency_leases(provider_id, lease_until)
                """
            )

    def reserve(
        self,
        provider_id: str,
        requests_per_minute: int,
        max_wait_seconds: float,
    ) -> float:
        return self.reserve_capacity(
            provider_id,
            requests_per_minute,
            None,
            None,
            max_wait_seconds,
        )

    def wait(
        self,
        provider_id: str,
        requests_per_minute: int,
        max_wait_seconds: float,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> float:
        return self.wait_for_capacity(
            provider_id,
            requests_per_minute,
            None,
            None,
            max_wait_seconds,
            cancellation_token,
        )

    def reserve_capacity(
        self,
        provider_id: str,
        requests_per_minute: int,
        tokens_per_minute: Optional[int],
        token_count: Optional[int],
        max_wait_seconds: float,
    ) -> float:
        if not provider_id.strip() or requests_per_minute <= 0 or max_wait_seconds < 0:
            raise ValueError("provider rate limit arguments are invalid")
        if (tokens_per_minute is None) != (token_count is None):
            raise ValueError("provider token rate limit arguments are invalid")
        if tokens_per_minute is not None:
            if tokens_per_minute <= 0 or token_count is None or token_count <= 0:
                raise ValueError("provider token rate limit arguments are invalid")
            if token_count > tokens_per_minute:
                raise ProviderRateLimitExceeded(
                    "provider request token estimate exceeds the configured per-minute quota"
                )
        now = self.clock()
        request_interval = 60.0 / requests_per_minute
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            request_row = connection.execute(
                "SELECT next_slot_at FROM provider_rate_limits WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
            request_scheduled = max(
                now,
                request_row["next_slot_at"] if request_row is not None else now,
            )
            token_scheduled = now
            if tokens_per_minute is not None:
                token_row = connection.execute(
                    """
                    SELECT next_slot_at
                    FROM provider_token_rate_limits
                    WHERE provider_id = ?
                    """,
                    (provider_id,),
                ).fetchone()
                token_scheduled = max(
                    now,
                    token_row["next_slot_at"] if token_row is not None else now,
                )
            scheduled = max(request_scheduled, token_scheduled)
            delay = scheduled - now
            if delay > max_wait_seconds:
                raise ProviderRateLimitExceeded(
                    "provider quota wait would exceed the configured maximum"
                )
            connection.execute(
                """
                INSERT INTO provider_rate_limits(provider_id, next_slot_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    next_slot_at = excluded.next_slot_at,
                    updated_at = excluded.updated_at
                """,
                (provider_id, scheduled + request_interval, now),
            )
            if tokens_per_minute is not None and token_count is not None:
                connection.execute(
                    """
                    INSERT INTO provider_token_rate_limits(
                        provider_id, next_slot_at, updated_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(provider_id) DO UPDATE SET
                        next_slot_at = excluded.next_slot_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        provider_id,
                        scheduled + token_count * (60.0 / tokens_per_minute),
                        now,
                    ),
                )
        return delay

    def wait_for_capacity(
        self,
        provider_id: str,
        requests_per_minute: int,
        tokens_per_minute: Optional[int],
        token_count: Optional[int],
        max_wait_seconds: float,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> float:
        check_cancelled(cancellation_token)
        delay = self.reserve_capacity(
            provider_id,
            requests_per_minute,
            tokens_per_minute,
            token_count,
            max_wait_seconds,
        )
        self._wait(delay, cancellation_token)
        return delay

    def reserve_tokens(
        self,
        provider_id: str,
        tokens_per_minute: int,
        token_count: int,
        max_wait_seconds: float,
    ) -> float:
        if (
            not provider_id.strip()
            or tokens_per_minute <= 0
            or token_count <= 0
            or max_wait_seconds < 0
        ):
            raise ValueError("provider token rate limit arguments are invalid")
        if token_count > tokens_per_minute:
            raise ProviderRateLimitExceeded(
                "provider request token estimate exceeds the configured per-minute quota"
            )
        now = self.clock()
        interval = 60.0 / tokens_per_minute
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT next_slot_at
                FROM provider_token_rate_limits
                WHERE provider_id = ?
                """,
                (provider_id,),
            ).fetchone()
            scheduled = max(now, row["next_slot_at"] if row is not None else now)
            delay = max(0.0, scheduled - now)
            if delay > max_wait_seconds:
                raise ProviderRateLimitExceeded(
                    "provider token rate limit wait would exceed the configured maximum"
                )
            connection.execute(
                """
                INSERT INTO provider_token_rate_limits(
                    provider_id, next_slot_at, updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    next_slot_at = excluded.next_slot_at,
                    updated_at = excluded.updated_at
                """,
                (provider_id, scheduled + token_count * interval, now),
            )
        return delay

    def wait_for_tokens(
        self,
        provider_id: str,
        tokens_per_minute: int,
        token_count: int,
        max_wait_seconds: float,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> float:
        check_cancelled(cancellation_token)
        delay = self.reserve_tokens(
            provider_id, tokens_per_minute, token_count, max_wait_seconds
        )
        self._wait(delay, cancellation_token)
        return delay

    @contextmanager
    def concurrency_slot(
        self,
        provider_id: str,
        max_concurrent_requests: Optional[int],
        max_wait_seconds: float,
        lease_seconds: float,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Iterator[None]:
        if max_concurrent_requests is None:
            yield
            return
        if (
            not provider_id.strip()
            or max_concurrent_requests <= 0
            or max_wait_seconds < 0
            or lease_seconds <= 0
        ):
            raise ValueError("provider concurrency limit arguments are invalid")
        lease_id = uuid.uuid4().hex
        deadline = self.clock() + max_wait_seconds
        while True:
            check_cancelled(cancellation_token)
            now = self.clock()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    DELETE FROM provider_concurrency_leases
                    WHERE provider_id = ? AND lease_until <= ?
                    """,
                    (provider_id, now),
                )
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS lease_count, MIN(lease_until) AS next_expiry
                    FROM provider_concurrency_leases
                    WHERE provider_id = ?
                    """,
                    (provider_id,),
                ).fetchone()
                if row["lease_count"] < max_concurrent_requests:
                    connection.execute(
                        """
                        INSERT INTO provider_concurrency_leases(
                            provider_id, lease_id, lease_until, created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (provider_id, lease_id, now + lease_seconds, now),
                    )
                    break
                next_expiry = float(row["next_expiry"])
            remaining = deadline - now
            if remaining <= 0:
                raise ProviderRateLimitExceeded(
                    "provider concurrency wait would exceed the configured maximum"
                )
            delay = min(0.05, remaining, max(0.001, next_expiry - now))
            self._wait(delay, cancellation_token)
        try:
            check_cancelled(cancellation_token)
            yield
        finally:
            with self._connect() as connection:
                connection.execute(
                    """
                    DELETE FROM provider_concurrency_leases
                    WHERE provider_id = ? AND lease_id = ?
                    """,
                    (provider_id, lease_id),
                )

    def _wait(
        self,
        delay: float,
        cancellation_token: Optional[CancellationToken],
    ) -> None:
        if delay > 0:
            if cancellation_token is not None:
                cancellation_token.wait(delay)
            else:
                self.sleeper(delay)
        check_cancelled(cancellation_token)
