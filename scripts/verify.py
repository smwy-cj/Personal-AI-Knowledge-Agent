"""Run the repository's dependency-free acceptance checks."""

from __future__ import annotations

import compileall
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = PROJECT_ROOT / "tests"


def main() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))

    suite = unittest.defaultTestLoader.discover(str(TEST_ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    if not compileall.compile_dir(SOURCE_ROOT, quiet=1):
        return 1
    if not compileall.compile_dir(TEST_ROOT, quiet=1):
        return 1

    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(SOURCE_ROOT)
        if not existing_pythonpath
        else str(SOURCE_ROOT) + os.pathsep + existing_pythonpath
    )
    smoke = subprocess.run(
        [sys.executable, "-m", "personal_ai_agent", "--help"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    )
    if smoke.returncode != 0:
        return smoke.returncode

    with tempfile.TemporaryDirectory() as temporary:
        fixture_root = Path(temporary)
        fixture_vault = fixture_root / "vault"
        shutil.copytree(PROJECT_ROOT / "evaluations" / "fixtures" / "vault", fixture_vault)
        config_path = fixture_root / "agent.config.json"
        config_path.write_text(
            '{"vault_path":"vault","data_directory":"data",'
            '"managed_memory_directory":"Agent/Memory"}',
            encoding="utf-8",
        )
        sync = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "--config",
                str(config_path),
                "sync",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
        )
        if sync.returncode != 0:
            return sync.returncode
        cost_report = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "--config",
                str(config_path),
                "cost-report",
                "--include-calls",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if cost_report.returncode != 0:
            sys.stdout.write(cost_report.stdout)
            sys.stderr.write(cost_report.stderr)
            return cost_report.returncode
        cost_document = json.loads(cost_report.stdout)
        if (
            cost_document.get("schema") != "cost_report_v1"
            or cost_document.get("calls") != []
            or cost_document.get("totals", {}).get("model_call_count") != 0
        ):
            return 1
        statement_path = fixture_root / "empty-provider-statement.json"
        statement_path.write_text(
            json.dumps(
                {
                    "schema": "provider_billing_statement_v1",
                    "statement_id": "verification-empty-statement",
                    "provider_id": "verification-provider",
                    "currency": "USD",
                    "period": {
                        "from": "2026-01-01T00:00:00Z",
                        "to": "2027-01-01T00:00:00Z",
                    },
                    "total_billed_cost_microusd": 0,
                    "models": [],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        reconciliation = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "--config",
                str(config_path),
                "billing-reconcile",
                str(statement_path),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if reconciliation.returncode != 0:
            sys.stdout.write(reconciliation.stdout)
            sys.stderr.write(reconciliation.stderr)
            return reconciliation.returncode
        if not json.loads(reconciliation.stdout).get("reconciliation_passed"):
            return 1
        evaluation = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "--config",
                str(config_path),
                "eval-retrieval",
                str(PROJECT_ROOT / "evaluations" / "retrieval.example.json"),
                "--baseline",
                str(
                    PROJECT_ROOT
                    / "evaluations"
                    / "baselines"
                    / "retrieval.keyword.example.json"
                ),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if evaluation.returncode != 0:
            sys.stdout.write(evaluation.stdout)
            sys.stderr.write(evaluation.stderr)
            return evaluation.returncode
        report = json.loads(evaluation.stdout)
        evaluation_v2 = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "--config",
                str(config_path),
                "eval-retrieval",
                str(PROJECT_ROOT / "evaluations" / "retrieval.v2.example.json"),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if evaluation_v2.returncode != 0:
            sys.stdout.write(evaluation_v2.stdout)
            sys.stderr.write(evaluation_v2.stderr)
            return evaluation_v2.returncode
        report_v2 = json.loads(evaluation_v2.stdout)
        serialized_v2 = json.dumps(report_v2, ensure_ascii=False, sort_keys=True)
        if (
            report_v2.get("schema") != "retrieval_eval_report_v2"
            or report_v2.get("answer_case_count") != 7
            or report_v2.get("no_answer_case_count") != 1
            or "quantum cooking recipe" in serialized_v2
            or "checkpoint 恢复" in serialized_v2
        ):
            return 1
        report_path = fixture_root / "retrieval-report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        candidate = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "baseline-candidate",
                str(report_path),
                "--name",
                "example-keyword-retrieval-candidate-v2",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if candidate.returncode != 0:
            sys.stdout.write(candidate.stdout)
            sys.stderr.write(candidate.stderr)
            return candidate.returncode
        if json.loads(candidate.stdout).get("status") != "pending_review":
            return 1
        comparison = subprocess.run(
            [
                sys.executable,
                "-m",
                "personal_ai_agent",
                "baseline-compare",
                str(report_path),
                str(report_path),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if comparison.returncode != 0:
            sys.stdout.write(comparison.stdout)
            sys.stderr.write(comparison.stderr)
            return comparison.returncode
        comparison_report = json.loads(comparison.stdout)
        return 0 if not comparison_report["summary"]["regression_detected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
