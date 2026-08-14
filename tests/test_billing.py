import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.billing import (
    ProviderBillingStatement,
    reconcile_provider_billing,
)
from personal_ai_agent.observability import SQLiteEventStore


class ProviderBillingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = SQLiteEventStore(self.root / "events.sqlite3")

    def tearDown(self):
        self.temporary.cleanup()

    def statement(self, models=None, total=None):
        models = models if models is not None else [
            {
                "model_id": "model-a",
                "input_tokens": 100,
                "output_tokens": 20,
                "billed_cost_microusd": 300,
            }
        ]
        return {
            "schema": "provider_billing_statement_v1",
            "statement_id": "statement-2026-08",
            "provider_id": "provider-a",
            "currency": "USD",
            "period": {
                "from": "2026-08-01T00:00:00Z",
                "to": "2026-09-01T00:00:00Z",
            },
            "total_billed_cost_microusd": (
                sum(item["billed_cost_microusd"] for item in models)
                if total is None
                else total
            ),
            "models": models,
        }

    def write(self, document, name="private-statement.json"):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def record_call(self, cost=300, with_cost=True, model="model-a"):
        attributes = {
            "provider_id": "provider-a",
            "model_id": model,
            "task_type": "summary",
            "prompt_version": "v1",
            "input_tokens": 100,
            "output_tokens": 20,
            "duration_ms": 50,
            "model_call_count": 1,
        }
        if with_cost:
            attributes["estimated_cost_microusd"] = cost
        event_id = self.store.record(
            "model_completed", "task-a", "summary", attributes
        )
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE observation_events SET created_at = ? WHERE event_id = ?",
                ("2026-08-15T00:00:00+00:00", event_id),
            )

    def test_reconciles_matching_statement_and_omits_local_path(self):
        self.record_call()
        statement_path = self.write(self.statement())

        report = reconcile_provider_billing(self.store, statement_path)

        self.assertTrue(report["reconciliation_passed"])
        self.assertEqual(report["summary"]["difference_microusd"], 0)
        self.assertEqual(report["by_model"][0]["presence"], "matched")
        self.assertEqual(report["by_model"][0]["input_token_difference"], 0)
        self.assertEqual(len(report["statement"]["sha256"]), 64)
        self.assertIn("generated_at", report)
        self.assertNotIn(str(statement_path), json.dumps(report))

    def test_statement_fingerprint_normalizes_timezone_and_model_order(self):
        models = [
            {
                "model_id": "model-b",
                "input_tokens": 1,
                "output_tokens": 2,
                "billed_cost_microusd": 20,
            },
            {
                "model_id": "model-a",
                "input_tokens": 3,
                "output_tokens": 4,
                "billed_cost_microusd": 30,
            },
        ]
        first = self.statement(models=models)
        second = self.statement(models=list(reversed(models)))
        second["period"] = {
            "from": "2026-08-01T08:00:00+08:00",
            "to": "2026-09-01T08:00:00+08:00",
        }

        first_loaded = ProviderBillingStatement.load(self.write(first, "first.json"))
        second_loaded = ProviderBillingStatement.load(self.write(second, "second.json"))

        self.assertEqual(first_loaded.sha256, second_loaded.sha256)
        self.assertEqual(
            [item.model_id for item in first_loaded.models], ["model-a", "model-b"]
        )

    def test_applies_absolute_tolerance_and_flags_excess_difference(self):
        self.record_call(cost=400)
        statement_path = self.write(self.statement())
        within = reconcile_provider_billing(self.store, statement_path)
        self.assertTrue(within["reconciliation_passed"])
        self.assertEqual(within["summary"]["effective_tolerance_microusd"], 100)

        outside = reconcile_provider_billing(
            self.store, statement_path, absolute_tolerance_microusd=99
        )
        self.assertFalse(outside["reconciliation_passed"])
        self.assertEqual(outside["summary"]["model_failure_count"], 1)

    def test_fails_for_missing_models_and_missing_cost_estimates(self):
        self.record_call(with_cost=False, model="local-only")
        report = reconcile_provider_billing(self.store, self.write(self.statement()))

        self.assertFalse(report["reconciliation_passed"])
        self.assertEqual(report["summary"]["calls_without_cost_estimate"], 1)
        self.assertEqual(
            {item["presence"] for item in report["by_model"]},
            {"missing_local_model", "missing_statement_model"},
        )

    def test_strict_loader_rejects_invalid_currency_totals_duplicates_and_shape(self):
        document = self.statement()
        document["currency"] = "CNY"
        with self.assertRaises(ValueError):
            ProviderBillingStatement.load(self.write(document))

        with self.assertRaises(ValueError):
            ProviderBillingStatement.load(self.write(self.statement(total=301)))

        duplicate = self.statement()
        duplicate["models"].append(dict(duplicate["models"][0]))
        duplicate["total_billed_cost_microusd"] = 600
        with self.assertRaises(ValueError):
            ProviderBillingStatement.load(self.write(duplicate))

        extra = self.statement()
        extra["account_number"] = "not-accepted"
        with self.assertRaises(ValueError):
            ProviderBillingStatement.load(self.write(extra))

        namespaced = self.statement()
        namespaced["models"][0]["model_id"] = "namespace/model:v1@host"
        loaded = ProviderBillingStatement.load(self.write(namespaced))
        self.assertEqual(loaded.models[0].model_id, "namespace/model:v1@host")

    def test_rejects_invalid_tolerances(self):
        statement_path = self.write(self.statement(models=[], total=0))
        with self.assertRaises(ValueError):
            reconcile_provider_billing(
                self.store, statement_path, absolute_tolerance_microusd=-1
            )
        with self.assertRaises(ValueError):
            reconcile_provider_billing(
                self.store, statement_path, relative_tolerance=float("nan")
            )


if __name__ == "__main__":
    unittest.main()
