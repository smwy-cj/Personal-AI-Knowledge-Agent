"""SQLite persistence for current task state and checkpoint history."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Union

from .models import AgentTaskState, TaskStatus, utc_now
from .serialization import task_state_from_json, task_state_to_json


class TaskNotFound(KeyError):
    pass


@dataclass(frozen=True)
class CheckpointInfo:
    checkpoint_id: int
    task_id: str
    reason: str
    status: TaskStatus
    created_at: str


class SQLiteTaskRepository:
    """Owns one short-lived SQLite connection per operation.

    This keeps the repository safe to use from different application threads.
    SQLite WAL mode allows readers while a checkpoint is being written.
    """

    def __init__(self, database_path: Union[str, Path]) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_thread_updated
                    ON tasks(thread_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_checkpoints_task_id
                    ON task_checkpoints(task_id, checkpoint_id DESC);
                """
            )

    def save(self, state: AgentTaskState, reason: str) -> int:
        if not reason.strip():
            raise ValueError("checkpoint reason must be non-empty")
        checkpoint_time = utc_now()
        state.updated_at = checkpoint_time
        payload = task_state_to_json(state)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, thread_id, status, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    state.task_id,
                    state.thread_id,
                    state.status.value,
                    payload,
                    state.created_at,
                    checkpoint_time,
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO task_checkpoints(task_id, reason, status, state_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (state.task_id, reason, state.status.value, payload, checkpoint_time),
            )
            return int(cursor.lastrowid)

    def load(self, task_id: str) -> AgentTaskState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskNotFound(task_id)
        return task_state_from_json(row["state_json"])

    def load_checkpoint(self, checkpoint_id: int) -> AgentTaskState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM task_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        if row is None:
            raise TaskNotFound("checkpoint:%s" % checkpoint_id)
        return task_state_from_json(row["state_json"])

    def list_checkpoints(self, task_id: str) -> List[CheckpointInfo]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT checkpoint_id, task_id, reason, status, created_at
                FROM task_checkpoints
                WHERE task_id = ?
                ORDER BY checkpoint_id
                """,
                (task_id,),
            ).fetchall()
        return [
            CheckpointInfo(
                checkpoint_id=row["checkpoint_id"],
                task_id=row["task_id"],
                reason=row["reason"],
                status=TaskStatus(row["status"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_by_thread(self, thread_id: str, limit: int = 50) -> List[AgentTaskState]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT state_json FROM tasks
                WHERE thread_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (thread_id, limit),
            ).fetchall()
        return [task_state_from_json(row["state_json"]) for row in rows]

    def cancel_snapshot(self, task_id: str, reason: str = "cancellation requested") -> AgentTaskState:
        state = self.load(task_id)
        if state.status in {TaskStatus.COMPLETED, TaskStatus.PARTIAL_SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return state
        from .state_machine import transition

        transition(state, TaskStatus.CANCELLED, reason)
        self.save(state, "task_cancelled")
        return state
