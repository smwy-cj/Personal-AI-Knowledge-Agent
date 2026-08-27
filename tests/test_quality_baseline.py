import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.quality_baseline import (
    QualityBaselinePolicy,
    observability_baseline_scope,
    resolve_quality_baseline,
    retrieval_baseline_scope,
)


class QualityBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, document):
        path = self.root / "baseline.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def retrieval_document(self):
        return {
            "schema": "quality_baseline_v1",
            "name": "retrieval-v1",
            "scope": {
                "evaluation_type": "retrieval",
                "dataset_name": "dataset-v1",
                "engine": "keyword",
                "limit": 10,
                "provider_id": None,
            },
            "minimums": {"recall_at_k": 0.9},
            "maximums": {"p95_latency_ms": 250},
        }

    def test_loads_scope_bound_policy_and_merges_explicit_overrides(self):
        path = self.write(self.retrieval_document())
        policy = QualityBaselinePolicy.load(path)

        minimums, maximums, metadata = resolve_quality_baseline(
            str(path),
            retrieval_baseline_scope("dataset-v1", "keyword", 10, None),
            {"recall_at_k": 1.0},
            {"p50_latency_ms": 100},
        )

        self.assertEqual(policy.name, "retrieval-v1")
        self.assertEqual(minimums, {"recall_at_k": 1.0})
        self.assertEqual(
            maximums, {"p95_latency_ms": 250.0, "p50_latency_ms": 100}
        )
        self.assertEqual(metadata["name"], "retrieval-v1")
        self.assertNotIn(str(path), json.dumps(metadata))

    def test_rejects_scope_mismatch_unknown_metrics_and_non_finite_values(self):
        path = self.write(self.retrieval_document())
        with self.assertRaises(ValueError):
            resolve_quality_baseline(
                str(path),
                retrieval_baseline_scope("dataset-v1", "keyword", 5, None),
                {},
                {},
            )

        document = self.retrieval_document()
        document["maximums"] = {"estimated_cost_usd": 1}
        with self.assertRaises(ValueError):
            QualityBaselinePolicy.load(self.write(document))

        document = self.retrieval_document()
        document["maximums"] = {"p95_latency_ms": float("inf")}
        with self.assertRaises(ValueError):
            QualityBaselinePolicy.load(self.write(document))

    def test_observability_policy_uses_event_window_scope(self):
        document = {
            "schema": "quality_baseline_v1",
            "name": "operations-v1",
            "scope": {
                "evaluation_type": "observability",
                "event_limit": 1000,
            },
            "minimums": {"task_success_rate": 0.95},
            "maximums": {"estimated_cost_usd": 1.0},
        }
        path = self.write(document)
        policy = QualityBaselinePolicy.load(path)

        policy.require_scope(observability_baseline_scope(1000))
        with self.assertRaises(ValueError):
            policy.require_scope(observability_baseline_scope(100))

    def test_hybrid_policy_requires_an_explicit_provider(self):
        document = self.retrieval_document()
        document["scope"].update({"engine": "hybrid", "provider_id": None})
        with self.assertRaises(ValueError):
            QualityBaselinePolicy.load(self.write(document))

    def test_vector_policy_requires_and_preserves_an_explicit_provider(self):
        document = self.retrieval_document()
        document["scope"].update({"engine": "vector", "provider_id": None})
        with self.assertRaises(ValueError):
            QualityBaselinePolicy.load(self.write(document))

        document["scope"]["provider_id"] = "embed-local"
        policy = QualityBaselinePolicy.load(self.write(document))
        self.assertEqual(policy.scope["engine"], "vector")
        self.assertEqual(policy.scope["provider_id"], "embed-local")


if __name__ == "__main__":
    unittest.main()
