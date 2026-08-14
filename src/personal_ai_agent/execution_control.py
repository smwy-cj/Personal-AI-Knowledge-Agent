"""SQLite-backed execution leases, heartbeats and cancellation requests."""

import sqlite3
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Iterator, Optional, Union


class TaskLeaseConflict(ValueError):
    pass


class TaskLeaseLost(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionControlInfo:
    task_id: str
    owner_id: Optional[str]
    lease_until: Optional[str]
    heartbeat_at: Optional[str]
    cancel_requested: bool
    cancel_requested_at: Optional[str]


class SQLiteExecutionControl:
    def __init__(self, database_path: Union[str, Path]) -> None:
        self.database_path = str(database_path)
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
                CREATE TABLE IF NOT EXISTS task_execution_control (
                    task_id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    lease_until TEXT,
                    heartbeat_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    cancel_requested_at TEXT
                )
                """
            )

    def acquire(self, task_id: str, owner_id: str, lease_seconds: float) -> bool:
        _validate_lease(task_id, owner_id, lease_seconds)
        now = _now()
        lease_until = now + timedelta(seconds=lease_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT owner_id, lease_until FROM task_execution_control WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is not None and row["owner_id"] not in {None, owner_id}:
                active_until = _parse_time(row["lease_until"])
                if active_until is not None and active_until > now:
                    return False
            connection.execute(
                """
                INSERT INTO task_execution_control(
                    task_id, owner_id, lease_until, heartbeat_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    lease_until = excluded.lease_until,
                    heartbeat_at = excluded.heartbeat_at
                """,
                (task_id, owner_id, lease_until.isoformat(), now.isoformat()),
            )
        return True

    def heartbeat(self, task_id: str, owner_id: str, lease_seconds: float) -> None:
        _validate_lease(task_id, owner_id, lease_seconds)
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE task_execution_control
                SET heartbeat_at = ?, lease_until = ?
                WHERE task_id = ? AND owner_id = ? AND lease_until > ?
                """,
                (
                    now.isoformat(),
                    (now + timedelta(seconds=lease_seconds)).isoformat(),
                    task_id,
                    owner_id,
                    now.isoformat(),
                ),
            )
        if cursor.rowcount != 1:
            raise TaskLeaseLost("task execution lease is no longer owned")

    def release(self, task_id: str, owner_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_execution_control
                SET owner_id = NULL, lease_until = NULL
                WHERE task_id = ? AND owner_id = ?
                """,
                (task_id, owner_id),
            )

    def request_cancel(self, task_id: str) -> ExecutionControlInfo:
        now = _now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_execution_control(
                    task_id, cancel_requested, cancel_requested_at
                ) VALUES (?, 1, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    cancel_requested = 1,
                    cancel_requested_at = COALESCE(cancel_requested_at, excluded.cancel_requested_at)
                """,
                (task_id, now),
            )
        return self.get(task_id)

    def cancellation_requested(self, task_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM task_execution_control WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return bool(row is not None and row["cancel_requested"])

    def get(self, task_id: str) -> ExecutionControlInfo:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM task_execution_control WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return ExecutionControlInfo(task_id, None, None, None, False, None)
        return ExecutionControlInfo(
            task_id=row["task_id"],
            owner_id=row["owner_id"],
            lease_until=row["lease_until"],
            heartbeat_at=row["heartbeat_at"],
            cancel_requested=bool(row["cancel_requested"]),
            cancel_requested_at=row["cancel_requested_at"],
        )

    def lease(
        self,
        task_id: str,
        owner_id: str,
        lease_seconds: float = 30.0,
        heartbeat_seconds: Optional[float] = None,
    ) -> "ExecutionLease":
        return ExecutionLease(
            self,
            task_id,
            owner_id,
            lease_seconds,
            heartbeat_seconds or lease_seconds / 3.0,
        )


class ExecutionLease(AbstractContextManager):
    def __init__(
        self,
        control: SQLiteExecutionControl,
        task_id: str,
        owner_id: str,
        lease_seconds: float,
        heartbeat_seconds: float,
    ) -> None:
        if heartbeat_seconds <= 0 or heartbeat_seconds >= lease_seconds:
            raise ValueError("heartbeat interval must be positive and shorter than lease")
        self.control = control
        self.task_id = task_id
        self.owner_id = owner_id
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._stop = Event()
        self._failure: Optional[Exception] = None
        self._failure_lock = Lock()
        self._thread: Optional[Thread] = None

    def __enter__(self) -> "ExecutionLease":
        if not self.control.acquire(self.task_id, self.owner_id, self.lease_seconds):
            raise TaskLeaseConflict("task is already leased by another executor")
        self._thread = Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.heartbeat_seconds + 1.0))
        self.control.release(self.task_id, self.owner_id)
        return False

    def assert_owned(self) -> None:
        with self._failure_lock:
            failure = self._failure
        if failure is not None:
            raise TaskLeaseLost("task heartbeat failed") from failure

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self.control.heartbeat(
                    self.task_id, self.owner_id, self.lease_seconds
                )
            except Exception as exc:
                with self._failure_lock:
                    self._failure = exc
                self._stop.set()
                return


def _validate_lease(task_id: str, owner_id: str, lease_seconds: float) -> None:
    if not task_id.strip() or not owner_id.strip() or lease_seconds <= 0:
        raise ValueError("task_id, owner_id and lease_seconds must be valid")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None
