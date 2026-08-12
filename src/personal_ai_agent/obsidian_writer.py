"""Controlled, idempotent and drift-aware Obsidian memory writer."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Sequence, Union

from .memory_repository import MemoryRecord, ObsidianWriteReceipt, SQLiteMemoryRepository
from .obsidian import ObsidianVaultIngester, vault_id_for


MEMORY_ID_RE = re.compile(r"^memory_[a-f0-9]{32}$")


class ObsidianWriteError(ValueError):
    pass


class ObsidianContentDrift(ObsidianWriteError):
    pass


@dataclass(frozen=True)
class WriteOutcome:
    receipt: ObsidianWriteReceipt
    status: str


class ControlledObsidianWriter:
    def __init__(
        self,
        vault_root: Union[str, Path],
        managed_directory: str,
        memory_repository: SQLiteMemoryRepository,
    ) -> None:
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise ObsidianWriteError("vault root must be an existing directory")
        self.managed_relative = _validate_managed_directory(managed_directory)
        self.managed_root = (self.vault_root / Path(*self.managed_relative.parts)).resolve()
        _ensure_within(self.managed_root, self.vault_root)
        if ".obsidian" in {part.casefold() for part in self.managed_relative.parts}:
            raise ObsidianWriteError("managed directory cannot be inside .obsidian")
        self.managed_root.mkdir(parents=True, exist_ok=True)
        self.managed_root = self.managed_root.resolve()
        _ensure_within(self.managed_root, self.vault_root)
        self.vault_id = vault_id_for(self.vault_root)
        self.memory_repository = memory_repository

    def write(self, memory: MemoryRecord) -> WriteOutcome:
        if not MEMORY_ID_RE.fullmatch(memory.memory_id):
            raise ObsidianWriteError("memory id cannot be used as a managed filename")
        target = (self.managed_root / (memory.memory_id + ".md")).resolve()
        _ensure_within(target, self.managed_root)
        content = render_memory_note(memory)
        intended_hash = _hash_bytes(content.encode("utf-8"))
        relative_path = target.relative_to(self.vault_root).as_posix()
        receipt = self.memory_repository.get_write_receipt(memory.memory_id)

        if target.exists():
            if not target.is_file():
                raise ObsidianWriteError("managed target exists but is not a file")
            actual_hash = _hash_bytes(target.read_bytes())
            if receipt is not None:
                if receipt.vault_id != self.vault_id or receipt.relative_path != relative_path:
                    raise ObsidianWriteError("write receipt points to a different managed target")
                if actual_hash != receipt.content_hash:
                    raise ObsidianContentDrift("managed note changed after the last write")
                if actual_hash == intended_hash:
                    return WriteOutcome(receipt, "unchanged")
            elif actual_hash == intended_hash and _has_owner_marker(target, memory.memory_id):
                adopted = self.memory_repository.save_write_receipt(
                    memory.memory_id, self.vault_id, relative_path, intended_hash
                )
                return WriteOutcome(adopted, "adopted")
            else:
                raise ObsidianWriteError("refusing to overwrite an unmanaged existing note")

        if receipt is not None:
            raise ObsidianContentDrift("managed note was removed after the last write")

        _atomic_write(target, content)
        saved = self.memory_repository.save_write_receipt(
            memory.memory_id, self.vault_id, relative_path, intended_hash
        )
        return WriteOutcome(saved, "created")

    def write_many(self, memories: Sequence[MemoryRecord]) -> List[WriteOutcome]:
        return [self.write(memory) for memory in memories]


class ObsidianWritebackWorkflow:
    def __init__(
        self,
        writer: ControlledObsidianWriter,
        ingester: ObsidianVaultIngester,
    ) -> None:
        if writer.vault_root != ingester.vault_root:
            raise ValueError("writer and ingester must target the same vault")
        self.writer = writer
        self.ingester = ingester

    def __call__(self, state, step):
        from .models import Artifact, StepResult

        memory_ids = [
            candidate.candidate_id
            for candidate in state.memory_candidates
            if candidate.governance_status in {"PERSISTED", "VAULT_WRITTEN"}
        ]
        outcomes: List[WriteOutcome] = []
        for memory_id in memory_ids:
            record = self.writer.memory_repository.get(memory_id)
            if record is None:
                raise ObsidianWriteError("persisted candidate is missing from Memory Store")
            outcomes.append(self.writer.write(record))
        sync_result = self.ingester.sync()
        if sync_result.failed:
            raise ObsidianWriteError("vault reindex reported failed files")
        for candidate in state.memory_candidates:
            if candidate.candidate_id in memory_ids:
                candidate.governance_status = "VAULT_WRITTEN"
        receipt = {
            "schema": "obsidian_writeback_receipt_v1",
            "writes": [
                {
                    "memory_id": item.receipt.memory_id,
                    "vault_id": item.receipt.vault_id,
                    "relative_path": item.receipt.relative_path,
                    "content_hash": item.receipt.content_hash,
                    "status": item.status,
                }
                for item in outcomes
            ],
            "sync": sync_result.__dict__,
        }
        return StepResult(artifacts=[Artifact("obsidian_writeback_receipt", receipt)])


def register_obsidian_writeback_workflow(registry, writer, ingester) -> None:
    registry.register("obsidian.writeback", ObsidianWritebackWorkflow(writer, ingester))


def render_memory_note(memory: MemoryRecord) -> str:
    statement = memory.content.get("statement") if isinstance(memory.content, dict) else memory.content
    if not isinstance(statement, str) or not statement.strip():
        raise ObsidianWriteError("memory content has no non-empty statement")
    source_lines = "\n".join("  - %s" % json.dumps(item, ensure_ascii=False) for item in memory.source_ids)
    return (
        "---\n"
        "memory_id: %s\n"
        "memory_type: %s\n"
        "subject: %s\n"
        "normalized_hash: %s\n"
        "confidence: %s\n"
        "sources:\n%s\n"
        "tags: [agent-memory, managed]\n"
        "---\n\n"
        "# %s\n\n%s\n"
        % (
            memory.memory_id,
            json.dumps(memory.memory_type, ensure_ascii=False),
            json.dumps(memory.subject, ensure_ascii=False),
            memory.normalized_hash,
            memory.confidence,
            source_lines,
            memory.subject,
            statement.strip(),
        )
    )


def _validate_managed_directory(value: str) -> PurePosixPath:
    normalized = str(value).strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ObsidianWriteError("managed directory must be a safe relative path")
    return path


def _ensure_within(path: Path, parent: Path) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ObsidianWriteError("managed path escapes its allowed directory") from exc


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _has_owner_marker(path: Path, memory_id: str) -> bool:
    prefix = path.read_text(encoding="utf-8-sig")[:512]
    return ("memory_id: %s" % memory_id) in prefix


def _atomic_write(target: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % target.stem,
        suffix=".tmp",
        dir=str(target.parent),
        text=False,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary_path), str(target))
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
