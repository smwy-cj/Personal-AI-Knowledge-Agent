import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.hybrid_search import HybridSearchEngine
from personal_ai_agent.knowledge_repository import SQLiteKnowledgeRepository
from personal_ai_agent.models import AgentTaskState, PlanStep, TaskStatus
from personal_ai_agent.obsidian import ObsidianVaultIngester
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.research_workflow import (
    CitationIntegrityVerifier,
    register_research_workflow,
)
from personal_ai_agent.search import KeywordSearchEngine
from personal_ai_agent.vector import SQLiteVectorIndex


class ResearchEmbeddingProvider:
    provider_id = "research-test-v1"
    dimension = 3

    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vectors.append(
                [
                    float(lowered.count("memory") + lowered.count("记忆")),
                    float(lowered.count("evidence") + lowered.count("证据")),
                    1.0,
                ]
            )
        return vectors


class ResearchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.vault = root / "vault"
        self.vault.mkdir()
        (self.vault / "memory.md").write_text(
            "# Memory Governance\nLong-term memory requires evidence.\n"
            "## Approval\nUser approval is required before writing inferred preferences.\n",
            encoding="utf-8",
        )
        self.repository = SQLiteKnowledgeRepository(root / "knowledge.sqlite3")
        self.ingester = ObsidianVaultIngester(self.vault, self.repository)
        self.ingester.sync()
        vector = SQLiteVectorIndex(self.repository, ResearchEmbeddingProvider())
        vector.sync()
        self.search = HybridSearchEngine(KeywordSearchEngine(self.repository), vector)

    def tearDown(self):
        self.temp_directory.cleanup()

    def _orchestrator(self):
        registry = WorkflowRegistry()
        register_research_workflow(registry, self.search)
        return Orchestrator(
            registry, verifier=CitationIntegrityVerifier(self.repository)
        )

    def test_end_to_end_research_task_produces_verified_evidence_pack(self):
        state = AgentTaskState.create("thread-1", "memory evidence")
        result = self._orchestrator().run(
            state,
            [
                PlanStep(
                    "retrieve",
                    "research",
                    "research.retrieve",
                    inputs={"query": "memory evidence", "limit": 3},
                )
            ],
        )

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertGreaterEqual(len(result.evidence), 1)
        self.assertEqual(len(result.evidence), len(result.retrieved_context))
        pack = result.artifacts[0].content
        self.assertEqual("research_evidence_pack_v1", pack["schema"])
        self.assertEqual(len(result.evidence), pack["citation_count"])
        self.assertIn("memory.md:L1-L2", pack["markdown"])
        self.assertEqual([], result.errors)

    def test_verifier_rejects_tampered_evidence(self):
        state = AgentTaskState.create("thread-1", "memory evidence")
        result = self._orchestrator().run(
            state,
            [PlanStep("retrieve", "research", "research.retrieve")],
        )
        result.evidence[0].start_line = 999
        result.status = TaskStatus.VERIFYING

        verified = CitationIntegrityVerifier(self.repository)(result)

        self.assertFalse(verified)
        self.assertTrue(
            any(item.error_type == "CitationIntegrityError" for item in result.errors)
        )

    def test_verifier_rejects_tampered_artifact_citation(self):
        state = AgentTaskState.create("thread-1", "memory evidence")
        result = self._orchestrator().run(
            state,
            [PlanStep("retrieve", "research", "research.retrieve")],
        )
        result.artifacts[0].content["citations"][0]["relative_path"] = "fake.md"

        verified = CitationIntegrityVerifier(self.repository)(result)

        self.assertFalse(verified)
        self.assertTrue(any("relative_path" in item.message for item in result.errors))

    def test_verifier_detects_stale_chunk_after_note_changes(self):
        state = AgentTaskState.create("thread-1", "memory evidence")
        result = self._orchestrator().run(
            state,
            [PlanStep("retrieve", "research", "research.retrieve")],
        )
        (self.vault / "memory.md").write_text(
            "# Replaced\nThe previous evidence is gone.\n", encoding="utf-8"
        )
        self.ingester.sync()

        self.assertFalse(CitationIntegrityVerifier(self.repository)(result))

    def test_empty_retrieval_fails_without_fabricated_artifact(self):
        state = AgentTaskState.create("thread-1", "nonexistent-unique-term")
        result = self._orchestrator().run(
            state,
            [
                PlanStep(
                    "retrieve",
                    "research",
                    "research.retrieve",
                    inputs={"keyword_weight": 1.0, "vector_weight": 0.0},
                )
            ],
        )

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual([], result.artifacts)
        self.assertTrue(any("no supporting evidence" in item.message for item in result.errors))


if __name__ == "__main__":
    unittest.main()
