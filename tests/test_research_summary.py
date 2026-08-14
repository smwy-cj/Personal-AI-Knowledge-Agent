import tempfile
import unittest
from pathlib import Path
from typing import FrozenSet

from personal_ai_agent.hybrid_search import HybridSearchEngine
from personal_ai_agent.knowledge_repository import SQLiteKnowledgeRepository
from personal_ai_agent.model_gateway import ModelGateway, ProviderResponse
from personal_ai_agent.models import AgentTaskState, PlanStep, TaskBudget, TaskStatus
from personal_ai_agent.obsidian import ObsidianVaultIngester
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.research_summary import (
    CompositeVerifier,
    ResearchSummaryVerifier,
    register_research_summary_workflow,
)
from personal_ai_agent.research_workflow import CitationIntegrityVerifier, register_research_workflow
from personal_ai_agent.search import KeywordSearchEngine
from personal_ai_agent.vector import SQLiteVectorIndex


class Embedding:
    provider_id = "summary-embedding-v1"
    dimension = 2

    def embed(self, texts):
        return [[float(text.casefold().count("memory") + 1), 1.0] for text in texts]


class SummaryProvider:
    provider_id = "summary-provider"
    capabilities: FrozenSet[str] = frozenset({"structured_output"})

    def __init__(self, data):
        self.data = data
        self.last_request = None

    def generate(self, request):
        self.last_request = request
        return ProviderResponse(self.data, "summary-model-v1", 20, 10)


class ResearchSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        vault = root / "vault"
        vault.mkdir()
        (vault / "memory.md").write_text(
            "# Memory\nMemory writes require evidence and approval.\n", encoding="utf-8"
        )
        self.repository = SQLiteKnowledgeRepository(root / "knowledge.sqlite3")
        ObsidianVaultIngester(vault, self.repository).sync()
        vector = SQLiteVectorIndex(self.repository, Embedding())
        vector.sync()
        self.search = HybridSearchEngine(KeywordSearchEngine(self.repository), vector)

    def tearDown(self):
        self.temp_directory.cleanup()

    def _run(self, summary_data):
        provider = SummaryProvider(summary_data)
        gateway = ModelGateway([provider])
        registry = WorkflowRegistry()
        register_research_workflow(registry, self.search)
        register_research_summary_workflow(registry, gateway)
        verifier = CompositeVerifier(
            CitationIntegrityVerifier(self.repository), ResearchSummaryVerifier()
        )
        state = Orchestrator(registry, verifier=verifier).run(
            AgentTaskState.create("thread-1", "memory evidence"),
            [
                PlanStep("retrieve", "research", "research.retrieve"),
                PlanStep(
                    "summarize",
                    "generate",
                    "research.summarize",
                    depends_on=("retrieve",),
                ),
            ],
        )
        return state, provider

    def test_generates_verified_summary_and_model_trace(self):
        state, provider = self._run(
            {
                "title": "Memory Governance",
                "sections": [
                    {
                        "heading": "Conclusion",
                        "paragraphs": [
                            {"text": "Memory writes need evidence and approval.", "citations": [1]}
                        ],
                    }
                ],
            }
        )

        self.assertEqual(TaskStatus.COMPLETED, state.status)
        self.assertIn("[1]", state.final_answer)
        self.assertEqual(30, state.token_usage)
        self.assertEqual(1, len(state.model_calls))
        self.assertEqual("research_summary", state.model_calls[0].task_type)
        self.assertEqual(1, provider.last_request.payload["evidence"][0]["citation_id"])

    def test_unknown_citation_fails_before_artifact_is_added(self):
        state, _ = self._run(
            {
                "title": "Invalid",
                "sections": [
                    {"heading": "Bad", "paragraphs": [{"text": "Unsupported", "citations": [99]}]}
                ],
            }
        )
        self.assertEqual(TaskStatus.FAILED, state.status)
        self.assertFalse(any(item.artifact_type == "research_summary" for item in state.artifacts))

    def test_uncited_paragraph_fails_schema_validation(self):
        state, _ = self._run(
            {
                "title": "Invalid",
                "sections": [
                    {"heading": "Bad", "paragraphs": [{"text": "No source", "citations": []}]}
                ],
            }
        )
        self.assertEqual(TaskStatus.FAILED, state.status)

    def test_model_is_not_called_when_token_budget_is_exhausted(self):
        provider = SummaryProvider(
            {"title": "Unused", "sections": []}
        )
        gateway = ModelGateway([provider])
        registry = WorkflowRegistry()
        register_research_workflow(registry, self.search)
        register_research_summary_workflow(registry, gateway)
        state = AgentTaskState.create(
            "thread-1", "memory evidence", budget=TaskBudget(max_tokens=0)
        )
        result = Orchestrator(registry).run(
            state,
            [
                PlanStep("retrieve", "research", "research.retrieve"),
                PlanStep(
                    "summarize",
                    "generate",
                    "research.summarize",
                    depends_on=("retrieve",),
                ),
            ],
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIsNone(provider.last_request)


if __name__ == "__main__":
    unittest.main()
