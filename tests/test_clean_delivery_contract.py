import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CleanDeliveryContractTests(unittest.TestCase):
    def test_secret_scanner_exists_and_has_no_third_party_dependency(self):
        scanner = (ROOT / "scripts" / "scan_secrets.py").read_text(encoding="utf-8")
        self.assertIn("git", scanner)
        self.assertIn("working-tree", scanner)
        self.assertIn("git-history", scanner)
        self.assertNotIn("requests", scanner)
        self.assertNotIn("yaml", scanner)

    def test_clean_verification_image_is_independent_and_runs_acceptance(self):
        dockerfile = (ROOT / "Dockerfile.verify").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.12-slim", dockerfile)
        self.assertRegex(dockerfile, r"python -m pip install(?: --no-cache-dir)? \.")
        self.assertTrue(
            "python scripts/verify.py" in dockerfile
            or "python -m scripts.verify" in dockerfile
        )
        self.assertTrue(
            "python scripts/scan_secrets.py --working-tree" in dockerfile
            or "python -m scripts.scan_secrets --working-tree" in dockerfile
        )
        self.assertNotIn("COPY . .", dockerfile)

    def test_ci_runs_secret_scan_before_unit_tests(self):
        ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        job = ci[ci.index("unit-test:") : ci.index("package-build:")]
        scan_position = job.index("python scripts/scan_secrets.py --working-tree")
        verify_position = job.index("python scripts/verify.py")
        self.assertLess(scan_position, verify_position)

    def test_ignore_rules_exclude_local_secret_and_scan_outputs(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for entry in (".env", ".env.*", "!.env.example", "secret-scan-report.json"):
            self.assertIn(entry, ignored)


if __name__ == "__main__":
    unittest.main()
