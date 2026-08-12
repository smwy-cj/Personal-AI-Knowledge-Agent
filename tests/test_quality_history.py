import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.quality_baseline import QualityBaselinePolicy
from personal_ai_agent.quality_history import (
    compare_quality_reports,
    generate_quality_baseline_candidate,
)


class QualityHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, document):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def retrieval_report(self, **overrides):
        report = {
            "schema": "retrieval_eval_report_v1",
            "dataset_name": "retrieval-v1",
            "engine": "keyword",
            "limit": 10,
            "case_count": 4,
            "recall_at_k": 1.0,
            "hit_rate_at_k": 0.75,
            "mrr_at_k": 0.8,
            "p50_latency_ms": 100,
            "p95_latency_ms": 200,
            "evaluation_scope": {
                "evaluation_type": "retrieval",
                "dataset_name": "retrieval-v1",
                "engine": "keyword",
                "limit": 10,
                "provider_id": None,
            },
            "cases": [{"case_id": "safe-case"}],
        }
        report.update(overrides)
        return report

    def test_generates_pending_candidate_with_review_margins_and_no_path(self):
        source = self.write("private-report.json", self.retrieval_report())

        candidate = generate_quality_baseline_candidate(
            source, "retrieval-candidate-v2"
        )

        self.assertEqual(candidate["status"], "pending_review")
        self.assertEqual(candidate["proposed_policy"]["minimums"]["recall_at_k"], 0.98)
        self.assertEqual(candidate["proposed_policy"]["maximums"]["p95_latency_ms"], 240.0)
        self.assertNotIn("cases", candidate)
        self.assertNotIn(str(source), json.dumps(candidate))
        QualityBaselinePolicy.from_document(candidate["proposed_policy"])

    def test_generates_observability_candidate_and_rejects_invalid_parameters(self):
        report = {
            "schema": "observability_summary_v1",
            "evaluation_scope": {
                "evaluation_type": "observability",
                "event_limit": 1000,
            },
            "task_success_rate": 0.9,
            "estimated_cost_microusd": 1000,
            "estimated_cost_usd": 0.001,
            "step_p50_latency_ms": 10,
            "step_p95_latency_ms": 20,
            "model_p50_latency_ms": 30,
            "model_p95_latency_ms": 40,
        }
        source = self.write("operations.json", report)
        candidate = generate_quality_baseline_candidate(
            source, "operations-v2", 0.9, 1.5
        )
        self.assertEqual(
            candidate["proposed_policy"]["minimums"]["task_success_rate"], 0.81
        )
        self.assertEqual(
            candidate["proposed_policy"]["maximums"]["model_p95_latency_ms"], 60.0
        )
        with self.assertRaises(ValueError):
            generate_quality_baseline_candidate(source, "operations-v2", 1.1, 1.5)
        with self.assertRaises(ValueError):
            generate_quality_baseline_candidate(source, "operations-v2", 0.9, 0.9)

    def test_compares_metric_directions_and_reports_regressions(self):
        reference = self.write("reference.json", self.retrieval_report())
        current = self.write(
            "current.json",
            self.retrieval_report(
                recall_at_k=0.9,
                hit_rate_at_k=0.8,
                p50_latency_ms=80,
                p95_latency_ms=240,
            ),
        )

        comparison = compare_quality_reports(reference, current)

        self.assertTrue(comparison["summary"]["regression_detected"])
        self.assertEqual(comparison["metrics"]["recall_at_k"]["outcome"], "degraded")
        self.assertEqual(comparison["metrics"]["hit_rate_at_k"]["outcome"], "improved")
        self.assertEqual(comparison["metrics"]["p50_latency_ms"]["outcome"], "improved")
        self.assertEqual(comparison["metrics"]["p95_latency_ms"]["outcome"], "degraded")
        self.assertEqual(comparison["metrics"]["mrr_at_k"]["outcome"], "unchanged")
        self.assertNotIn(str(reference), json.dumps(comparison))

    def test_rejects_scope_mismatch_missing_metrics_and_unknown_schema(self):
        reference = self.write("reference.json", self.retrieval_report())
        changed_scope = self.retrieval_report(limit=5)
        changed_scope["evaluation_scope"]["limit"] = 5
        current = self.write("current.json", changed_scope)
        with self.assertRaises(ValueError):
            compare_quality_reports(reference, current)

        missing = self.retrieval_report()
        del missing["recall_at_k"]
        with self.assertRaises(ValueError):
            generate_quality_baseline_candidate(
                self.write("missing.json", missing), "missing-v1"
            )

        unknown = self.retrieval_report(schema="unknown_report_v1")
        with self.assertRaises(ValueError):
            generate_quality_baseline_candidate(
                self.write("unknown.json", unknown), "unknown-v1"
            )


if __name__ == "__main__":
    unittest.main()
