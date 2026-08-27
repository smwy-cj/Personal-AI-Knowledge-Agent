import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.quality_evaluation import (
    MemoryGovernanceEvaluationDataset,
    ResearchSummaryEvaluationDataset,
    apply_observability_gates,
    apply_retrieval_gates,
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

    def test_retrieval_gates_support_quality_minimums_and_latency_maximums(self):
        report = apply_retrieval_gates(
            {
                "recall_at_k": 0.8,
                "hit_rate_at_k": 1.0,
                "mrr_at_k": 0.7,
                "p50_latency_ms": 20,
                "p95_latency_ms": 120,
            },
            {"recall_at_k": 0.9},
            {"p95_latency_ms": 100},
        )

        self.assertFalse(report["gate_passed"])
        self.assertEqual(report["failed_gates"], ["recall_at_k", "p95_latency_ms"])
        self.assertEqual(
            report["gate_thresholds"],
            {
                "minimums": {"recall_at_k": 0.9},
                "maximums": {"p95_latency_ms": 100},
            },
        )

    def test_retrieval_v2_gates_chunk_recall_and_no_answer_false_positives(self):
        report = apply_retrieval_gates(
            {
                "schema": "retrieval_eval_report_v2",
                "recall_at_k": 1.0,
                "hit_rate_at_k": 1.0,
                "mrr_at_k": 1.0,
                "chunk_recall_at_k": 0.5,
                "no_answer_false_positive_rate": 0.25,
                "p50_latency_ms": 20,
                "p95_latency_ms": 40,
            },
            {"chunk_recall_at_k": 0.75},
            {"no_answer_false_positive_rate": 0.1},
        )

        self.assertFalse(report["gate_passed"])
        self.assertEqual(
            report["failed_gates"],
            ["chunk_recall_at_k", "no_answer_false_positive_rate"],
        )

    def test_observability_gates_bound_success_latency_and_cost(self):
        report = apply_observability_gates(
            {
                "task_success_rate": 0.75,
                "estimated_cost_microusd": 250,
                "estimated_cost_usd": 0.00025,
                "step_p50_latency_ms": 20,
                "step_p95_latency_ms": 100,
                "model_p50_latency_ms": 40,
                "model_p95_latency_ms": 80,
                "provider_quota_p95_wait_ms": 120,
                "provider_cooldown_count": 2,
                "provider_token_estimate_absolute_error": 15,
            },
            {"task_success_rate": 0.8},
            {
                "estimated_cost_microusd": 200,
                "model_p95_latency_ms": 100,
                "provider_quota_p95_wait_ms": 100,
            },
        )

        self.assertFalse(report["gate_passed"])
        self.assertEqual(
            report["failed_gates"],
            [
                "task_success_rate",
                "estimated_cost_microusd",
                "provider_quota_p95_wait_ms",
            ],
        )

    def test_directional_gate_whitelists_and_finite_thresholds_are_enforced(self):
        retrieval = {
            "recall_at_k": 1.0,
            "hit_rate_at_k": 1.0,
            "mrr_at_k": 1.0,
            "p50_latency_ms": 1,
            "p95_latency_ms": 2,
        }
        with self.assertRaises(ValueError):
            apply_retrieval_gates(retrieval, {}, {"recall_at_k": 1.0})
        with self.assertRaises(ValueError):
            apply_retrieval_gates(retrieval, {}, {"p95_latency_ms": float("inf")})


if __name__ == "__main__":
    unittest.main()
