import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.quality_evaluation import (
    MemoryGovernanceEvaluationDataset,
    ResearchSummaryEvaluationDataset,
    evaluate_memory_governance,
    evaluate_research_summaries,
)


class QualityEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, document):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_research_metrics_use_human_citation_labels_and_gate(self):
        path = self.write(
            "research.json",
            {
                "schema": "research_summary_eval_v1",
                "name": "research-baseline",
                "cases": [
                    {
                        "case_id": "summary-1",
                        "citation_count": 3,
                        "summary": {
                            "title": "Result",
                            "sections": [
                                {
                                    "heading": "Findings",
                                    "paragraphs": [
                                        {"text": "First fact.", "citations": [1, 2]},
                                        {"text": "Second fact.", "citations": [2]},
                                    ],
                                }
                            ],
                        },
                        "expected_paragraph_citations": [[1], [3]],
                    }
                ],
            },
        )

        report = evaluate_research_summaries(
            ResearchSummaryEvaluationDataset.load(path),
            {"citation_f1": 0.5, "exact_citation_set_rate": 0.1},
        )

        self.assertEqual(report.structure_valid_rate, 1.0)
        self.assertEqual(report.paragraph_coverage_rate, 1.0)
        self.assertEqual(report.exact_citation_set_rate, 0.0)
        self.assertEqual(report.citation_precision, 1 / 3)
        self.assertEqual(report.citation_recall, 0.5)
        self.assertEqual(report.citation_f1, 0.4)
        self.assertFalse(report.gate_passed)
        self.assertEqual(
            report.failed_gates, ["citation_f1", "exact_citation_set_rate"]
        )
        serialized = json.dumps(report.as_dict())
        self.assertNotIn("First fact", serialized)

    def test_memory_governance_labels_cover_pending_sensitive_duplicate_and_conflict(self):
        path = self.write(
            "memory.json",
            {
                "schema": "memory_governance_eval_v1",
                "name": "memory-baseline",
                "cases": [
                    {
                        "case_id": "pending",
                        "subject": "policy",
                        "statement": "Memory requires approval.",
                        "source_ids": ["chunk-1"],
                        "existing_memories": [],
                        "expected_status": "PENDING",
                        "expected_reason": None,
                        "expected_requires_approval": True,
                    },
                    {
                        "case_id": "sensitive",
                        "subject": "policy",
                        "statement": "api_key = sk-abcdefghijklmnop",
                        "source_ids": ["chunk-1"],
                        "existing_memories": [],
                        "expected_status": "REJECTED",
                        "expected_reason": "sensitive_content",
                        "expected_requires_approval": False,
                    },
                    {
                        "case_id": "duplicate",
                        "subject": "policy",
                        "statement": "Memory requires approval.",
                        "source_ids": ["chunk-2"],
                        "existing_memories": [
                            {
                                "subject": "policy",
                                "statement": "Memory requires approval.",
                                "source_ids": ["chunk-1"],
                            }
                        ],
                        "expected_status": "REJECTED",
                        "expected_reason": "duplicate",
                        "expected_requires_approval": False,
                    },
                    {
                        "case_id": "conflict",
                        "subject": "policy",
                        "statement": "Memory may be automatic.",
                        "source_ids": ["chunk-2"],
                        "existing_memories": [
                            {
                                "subject": "policy",
                                "statement": "Memory requires approval.",
                                "source_ids": ["chunk-1"],
                            }
                        ],
                        "expected_status": "PENDING",
                        "expected_reason": "conflict_requires_approval",
                        "expected_requires_approval": True,
                    },
                ],
            },
        )

        report = evaluate_memory_governance(
            MemoryGovernanceEvaluationDataset.load(path),
            {"decision_accuracy": 1.0},
        )

        self.assertEqual(report.decision_accuracy, 1.0)
        self.assertEqual(report.status_accuracy, 1.0)
        self.assertEqual(report.reason_accuracy, 1.0)
        self.assertEqual(report.approval_accuracy, 1.0)
        self.assertTrue(report.gate_passed)
        serialized = json.dumps(report.as_dict())
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("Memory requires approval", serialized)

    def test_rejects_invalid_gate_names_and_thresholds(self):
        path = self.write(
            "research.json",
            {
                "schema": "research_summary_eval_v1",
                "name": "research-baseline",
                "cases": [
                    {
                        "case_id": "summary-1",
                        "citation_count": 1,
                        "summary": {
                            "title": "Result",
                            "sections": [
                                {
                                    "heading": "Findings",
                                    "paragraphs": [
                                        {"text": "Fact.", "citations": [1]}
                                    ],
                                }
                            ],
                        },
                        "expected_paragraph_citations": [[1]],
                    }
                ],
            },
        )
        dataset = ResearchSummaryEvaluationDataset.load(path)
        with self.assertRaises(ValueError):
            evaluate_research_summaries(dataset, {"unknown": 1.0})
        with self.assertRaises(ValueError):
            evaluate_research_summaries(dataset, {"citation_f1": 1.1})


if __name__ == "__main__":
    unittest.main()
