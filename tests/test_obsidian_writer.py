import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.knowledge_repository import SQLiteKnowledgeRepository
from personal_ai_agent.memory_repository import SQLiteMemoryRepository
from personal_ai_agent.models import AgentTaskState, MemoryCandidate, PlanStep, TaskStatus
from personal_ai_agent.obsidian import ObsidianVaultIngester
from personal_ai_agent.obsidian_writer import (
    ControlledObsidianWriter,
    ObsidianContentDrift,
    ObsidianWriteError,
    ObsidianWritebackWorkflow,
)
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry


def persisted_memory(repository, statement="Memory requires approval."):
    candidate = MemoryCandidate(
        "semantic",
        {"statement": statement},
        ["chunk-1"],
        1.0,
        True,
        subject="policy",
        normalized_hash="a" * 64,
        governance_status="APPROVED",
    )
    repository.save_approved(candidate)
    candidate.governance_status = "PERSISTED"
    return candidate


class ObsidianWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.vault = root / "vault"
        self.vault.mkdir()
        self.memory_repository = SQLiteMemoryRepository(root / "memory.sqlite3")
        self.knowledge_repository = SQLiteKnowledgeRepository(root / "knowledge.sqlite3")
        self.ingester = ObsidianVaultIngester(self.vault, self.knowledge_repository)
        self.writer = ControlledObsidianWriter(
            self.vault, "Agent/Memory", self.memory_repository
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_atomic_write_is_idempotent_and_reindexed(self):
        candidate = persisted_memory(self.memory_repository)
        record = self.memory_repository.get(candidate.candidate_id)
        first = self.writer.write(record)
        second = self.writer.write(record)
        sync = self.ingester.sync()

        self.assertEqual("created", first.status)
        self.assertEqual("unchanged", second.status)
        self.assertEqual(first.receipt.content_hash, second.receipt.content_hash)
        self.assertEqual(1, sync.added)
        document = self.knowledge_repository.get_document_by_path(
            self.ingester.vault_id, first.receipt.relative_path
        )
        self.assertIsNotNone(document)
        self.assertEqual(candidate.candidate_id, document.frontmatter["memory_id"])
        self.assertEqual([], list((self.vault / "Agent" / "Memory").glob("*.tmp")))

    def test_user_edit_causes_drift_and_is_not_overwritten(self):
        candidate = persisted_memory(self.memory_repository)
        record = self.memory_repository.get(candidate.candidate_id)
        outcome = self.writer.write(record)
        path = self.vault / Path(outcome.receipt.relative_path)
        path.write_text("user edit", encoding="utf-8")

        with self.assertRaises(ObsidianContentDrift):
            self.writer.write(record)
        self.assertEqual("user edit", path.read_text(encoding="utf-8"))

    def test_user_deletion_is_treated_as_drift_not_recreated(self):
        candidate = persisted_memory(self.memory_repository)
        record = self.memory_repository.get(candidate.candidate_id)
        outcome = self.writer.write(record)
        path = self.vault / Path(outcome.receipt.relative_path)
        path.unlink()

        with self.assertRaises(ObsidianContentDrift):
            self.writer.write(record)
        self.assertFalse(path.exists())

    def test_unmanaged_collision_is_rejected(self):
        candidate = persisted_memory(self.memory_repository)
        target = self.vault / "Agent" / "Memory" / (candidate.candidate_id + ".md")
        target.write_text("unmanaged", encoding="utf-8")
        with self.assertRaises(ObsidianWriteError):
            self.writer.write(self.memory_repository.get(candidate.candidate_id))

    def test_path_traversal_and_obsidian_directory_are_rejected(self):
        for path in ("../escape", "/absolute", ".obsidian/generated"):
            with self.subTest(path=path):
                with self.assertRaises(ObsidianWriteError):
                    ControlledObsidianWriter(self.vault, path, self.memory_repository)

    def test_workflow_writes_only_persisted_memory_and_returns_receipt(self):
        candidate = persisted_memory(self.memory_repository)
        state = AgentTaskState.create("thread-1", "write memory")
        state.memory_candidates = [candidate]
        registry = WorkflowRegistry()
        registry.register(
            "obsidian.writeback", ObsidianWritebackWorkflow(self.writer, self.ingester)
        )

        result = Orchestrator(registry).run(
            state, [PlanStep("write", "memory", "obsidian.writeback")]
        )

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual("VAULT_WRITTEN", result.memory_candidates[0].governance_status)
        receipt = result.artifacts[0].content
        self.assertEqual("obsidian_writeback_receipt_v1", receipt["schema"])
        self.assertEqual(1, receipt["sync"]["added"])


if __name__ == "__main__":
    unittest.main()
