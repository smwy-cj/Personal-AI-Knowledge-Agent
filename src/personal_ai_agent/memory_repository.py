"""SQLite persistence for governed long-term semantic memories."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Union

from .models import MemoryCandidate, utc_now


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    memory_type: str
    subject: str
    content: object
    source_ids: List[str]
    normalized_hash: str
    confidence: float
    created_at: str


@dataclass(frozen=True)
class ObsidianWriteReceipt:
    memory_id: str
    vault_id: str
    relative_path: str
    content_hash: str
    written_at: str


class SQLiteMemoryRepository:
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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS semantic_memories (
                    memory_id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    normalized_hash TEXT NOT NULL UNIQUE,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_memories_subject
                    ON semantic_memories(memory_type, subject);

                CREATE TABLE IF NOT EXISTS obsidian_write_receipts (
                    memory_id TEXT PRIMARY KEY,
                    vault_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    written_at TEXT NOT NULL,
                    FOREIGN KEY(memory_id) REFERENCES semantic_memories(memory_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_obsidian_receipt_path
                    ON obsidian_write_receipts(vault_id, relative_path);
                """
            )

    def get(self, memory_id: str) -> Optional[MemoryRecord]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        return _record(row) if row else None

    def find_by_hash(self, normalized_hash: str) -> Optional[MemoryRecord]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE normalized_hash = ?",
                (normalized_hash,),
            ).fetchone()
        return _record(row) if row else None

    def find_by_subject(self, memory_type: str, subject: str) -> List[MemoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM semantic_memories
                WHERE memory_type = ? AND subject = ?
                ORDER BY created_at, memory_id
                """,
                (memory_type, subject),
            ).fetchall()
        return [_record(row) for row in rows]

    def save_approved(self, candidate: MemoryCandidate) -> MemoryRecord:
        if candidate.governance_status != "APPROVED":
            raise ValueError("only approved memory candidates may be persisted")
        if not candidate.subject or not candidate.normalized_hash:
            raise ValueError("approved memory candidate lacks governance metadata")
        created_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO semantic_memories(
                    memory_id, memory_type, subject, content_json, source_ids_json,
                    normalized_hash, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    candidate.memory_type,
                    candidate.subject,
                    json.dumps(candidate.content, ensure_ascii=False, sort_keys=True),
                    json.dumps(candidate.source_ids, ensure_ascii=False),
                    candidate.normalized_hash,
                    candidate.confidence,
                    created_at,
                ),
            )
        return MemoryRecord(
            candidate.candidate_id,
            candidate.memory_type,
            candidate.subject,
            candidate.content,
            list(candidate.source_ids),
            candidate.normalized_hash,
            candidate.confidence,
            created_at,
        )

    def list_all(self) -> List[MemoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM semantic_memories ORDER BY created_at, memory_id"
            ).fetchall()
        return [_record(row) for row in rows]

    def get_write_receipt(self, memory_id: str) -> Optional[ObsidianWriteReceipt]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM obsidian_write_receipts WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        return _receipt(row) if row else None

    def save_write_receipt(
        self,
        memory_id: str,
        vault_id: str,
        relative_path: str,
        content_hash: str,
    ) -> ObsidianWriteReceipt:
        if self.get(memory_id) is None:
            raise ValueError("cannot create receipt for an unknown memory")
        written_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO obsidian_write_receipts(
                    memory_id, vault_id, relative_path, content_hash, written_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    vault_id = excluded.vault_id,
                    relative_path = excluded.relative_path,
                    content_hash = excluded.content_hash,
                    written_at = excluded.written_at
                """,
                (memory_id, vault_id, relative_path, content_hash, written_at),
            )
        return ObsidianWriteReceipt(
            memory_id, vault_id, relative_path, content_hash, written_at
        )


def _record(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row["memory_id"],
        memory_type=row["memory_type"],
        subject=row["subject"],
        content=json.loads(row["content_json"]),
        source_ids=json.loads(row["source_ids_json"]),
        normalized_hash=row["normalized_hash"],
        confidence=row["confidence"],
        created_at=row["created_at"],
    )


def _receipt(row: sqlite3.Row) -> ObsidianWriteReceipt:
    return ObsidianWriteReceipt(
        memory_id=row["memory_id"],
        vault_id=row["vault_id"],
        relative_path=row["relative_path"],
        content_hash=row["content_hash"],
        written_at=row["written_at"],
    )
