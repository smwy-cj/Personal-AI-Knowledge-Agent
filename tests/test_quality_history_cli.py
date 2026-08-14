import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from personal_ai_agent.cli import main


class QualityHistoryCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def report(self, name, recall=1.0, latency=100):
        path = self.root / name
        path.write_text(
            json.dumps(
                {
                    "schema": "retrieval_eval_report_v1",
                    "dataset_name": "cli-history-v1",
                    "engine": "keyword",
                    "limit": 10,
                    "recall_at_k": recall,
                    "hit_rate_at_k": 1.0,
                    "mrr_at_k": 1.0,
                    "p50_latency_ms": latency,
                    "p95_latency_ms": latency,
                    "evaluation_scope": {
                        "evaluation_type": "retrieval",
                        "dataset_name": "cli-history-v1",
                        "engine": "keyword",
                        "limit": 10,
                        "provider_id": None,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def invoke(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--config", str(self.root / "missing.json"), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_candidate_command_is_config_independent(self):
        report = self.report("report.json")
        code, output, errors = self.invoke(
            "baseline-candidate", str(report), "--name", "cli-candidate-v1"
        )
        self.assertEqual((code, errors), (0, ""))
        candidate = json.loads(output)
        self.assertEqual(candidate["status"], "pending_review")
        self.assertNotIn(str(report), output)

    def test_comparison_uses_exit_three_for_a_regression(self):
        reference = self.report("reference.json")
        current = self.report("current.json", recall=0.8, latency=120)
        code, output, errors = self.invoke(
            "baseline-compare", str(reference), str(current)
        )
        self.assertEqual((code, errors), (3, ""))
        comparison = json.loads(output)
        self.assertTrue(comparison["summary"]["regression_detected"])


if __name__ == "__main__":
    unittest.main()
