import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitLabCiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")

    def test_required_jobs_and_stages_exist(self):
        for stage in ("test", "package", "container", "deploy"):
            self.assertRegex(self.ci, r"(?m)^\s{2}- %s$" % stage)
        for job in ("unit-test", "package-build", "container-build", "deploy-demo"):
            self.assertRegex(self.ci, r"(?m)^%s:$" % re.escape(job))

    def test_unit_test_uses_one_click_verifier_without_paid_api_credentials(self):
        job = self._job("unit-test", "package-build")
        self.assertIn("python scripts/verify.py", job)
        self.assertIn("python -m pip install .", job)
        self.assertNotRegex(job, r"(?i)(api[_-]?key|password|model_key)\s*:")

    def test_package_job_builds_and_publishes_dist_artifacts(self):
        job = self._job("package-build", "container-build")
        self.assertIn("python -m build", job)
        self.assertRegex(job, r"(?m)^\s{4}paths:\s*\n\s{6}- dist/")
        self.assertIn("needs:", job)
        self.assertIn("unit-test", job)

    def test_container_job_builds_without_privileged_docker_daemon(self):
        job = self._job("container-build", "deploy-demo")
        self.assertIn("/kaniko/executor", job)
        self.assertIn("--no-push", job)
        self.assertNotIn("docker:dind", job)
        self.assertNotIn("privileged", job)
        self.assertIn("unit-test", job)

    def test_deploy_job_is_manual_protected_and_requires_external_url(self):
        job = self.ci[self.ci.index("deploy-demo:") :]
        self.assertIn("when: manual", job)
        self.assertIn("CI_COMMIT_TAG", job)
        self.assertIn("CI_COMMIT_REF_PROTECTED", job)
        self.assertIn("DEPLOY_WEBHOOK_URL", job)
        self.assertIn("DEMO_PUBLIC_URL", job)
        self.assertNotIn("echo $DEPLOY_WEBHOOK_URL", job)

    def test_ci_does_not_archive_private_runtime_or_environment_files(self):
        self.assertNotRegex(self.ci, r"(?m)^\s{6}- (data|course_demo/runtime|\.env)/?$")
        self.assertNotRegex(self.ci, r"(?i)(secret|token|password):\s*[^$\s]")

    def _job(self, start, end):
        return self.ci[self.ci.index(start + ":") : self.ci.index(end + ":")]


if __name__ == "__main__":
    unittest.main()
