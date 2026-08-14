import configparser
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionContractTests(unittest.TestCase):
    def test_python_package_declares_runtime_entrypoints_and_web_assets(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"waitress>=', pyproject)
        self.assertIn('personal-ai-agent-web = "personal_ai_agent.web_server:main"', pyproject)
        self.assertIn(
            'personal-ai-agent-demo = "personal_ai_agent.container_entrypoint:main"',
            pyproject,
        )
        self.assertIn('"web/templates/*.html"', pyproject)
        self.assertIn('"web/static/*.css"', pyproject)

    def test_docker_context_excludes_private_and_generated_data(self):
        ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        required = {".git", "data", "agent.config.json", "*.sqlite3", "__pycache__"}
        self.assertTrue(required.issubset({item.strip().rstrip("/") for item in ignored}))
        self.assertIn(".env", ignored)

    def test_image_uses_non_root_healthcheck_and_narrow_copy(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"(?m)^USER\s+(?!root\b)\S+")
        self.assertRegex(dockerfile, r"(?m)^HEALTHCHECK\b")
        self.assertNotRegex(dockerfile, r"(?m)^COPY\s+\.\s+")
        self.assertIn("personal-ai-agent-demo", dockerfile)
        self.assertNotIn("PERSONAL_AGENT_WEB_SECRET=", dockerfile)

    def test_demo_config_is_secret_free_and_paths_stay_in_demo_root(self):
        config_path = ROOT / "course_demo" / "config.json"
        document = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(document["vault_path"], "vault")
        self.assertEqual(document["data_directory"], "runtime")
        serialized = json.dumps(document).lower()
        for marker in ("api_key", "password", "secret", "token"):
            self.assertNotIn(marker, serialized)
        notes = list((ROOT / "course_demo" / "vault").glob("*.md"))
        self.assertGreaterEqual(len(notes), 3)

    def test_environment_example_contains_names_and_non_secret_placeholders(self):
        values = {}
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value
        self.assertEqual(values["PERSONAL_AGENT_DEMO_MODE"], "1")
        self.assertEqual(values["PERSONAL_AGENT_HTTPS"], "0")
        self.assertIn("replace", values["PERSONAL_AGENT_WEB_SECRET"].lower())
        self.assertLess(len(values["PERSONAL_AGENT_WEB_SECRET"]), 64)
        self.assertNotRegex(
            values["PERSONAL_AGENT_WEB_SECRET"], r"(?i)^(sk-|ghp_|glpat-|eyj)"
        )

    def test_compose_binds_localhost_and_uses_named_runtime_volume(self):
        compose = (ROOT / "docker-compose.example.yml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:8000:8000"', compose)
        self.assertIn("demo-runtime:/app/course_demo/runtime", compose)
        self.assertIn("${PERSONAL_AGENT_WEB_SECRET:?", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("tmpfs:", compose)
        self.assertNotIn("privileged: true", compose)

    def test_repository_has_a_real_license_file(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted", license_text)
        self.assertNotIn("TODO", license_text)


if __name__ == "__main__":
    unittest.main()
