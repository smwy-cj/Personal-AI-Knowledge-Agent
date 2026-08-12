"""SQLite-backed smooth provider rate limiting shared across processes."""

import sqlite3
import time
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

    def reserve(
        self,
        provider_id: str,
        requests_per_minute: int,
        max_wait_seconds: float,
    ) -> float:
        if not provider_id.strip() or requests_per_minute <= 0 or max_wait_seconds < 0:
            raise ValueError("provider rate limit arguments are invalid")
        now = self.clock()
        interval = 60.0 / requests_per_minute
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next_slot_at FROM provider_rate_limits WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
            scheduled = max(now, row["next_slot_at"] if row is not None else now)
            delay = max(0.0, scheduled - now)
            if delay > max_wait_seconds:
                raise ProviderRateLimitExceeded(
                    "provider rate limit wait would exceed the configured maximum"
                )
            connection.execute(
                """
                INSERT INTO provider_rate_limits(provider_id, next_slot_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    next_slot_at = excluded.next_slot_at,
                    updated_at = excluded.updated_at
                """,
                (provider_id, scheduled + interval, now),
            )
        return delay

    def wait(
        self,
        provider_id: str,
        requests_per_minute: int,
        max_wait_seconds: float,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> float:
        check_cancelled(cancellation_token)
        delay = self.reserve(provider_id, requests_per_minute, max_wait_seconds)
        if delay > 0:
            if cancellation_token is not None:
                cancellation_token.wait(delay)
            else:
                self.sleeper(delay)
        check_cancelled(cancellation_token)
        return delay
