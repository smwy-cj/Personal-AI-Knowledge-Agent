import unittest
from pathlib import Path
from unittest.mock import patch

from personal_ai_agent.web_server import build_parser


ROOT = Path(__file__).resolve().parents[1]


class RenderDeploymentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint_text = (ROOT / "render.yaml").read_text(encoding="utf-8")

    def test_blueprint_is_a_free_docker_web_service_with_health_check(self):
        for line in (
            "  - type: web",
            "    runtime: docker",
            "    plan: free",
            "    healthCheckPath: /health",
            "    dockerfilePath: ./Dockerfile",
            "    dockerContext: .",
        ):
            self.assertIn(line, self.blueprint_text)

    def test_blueprint_uses_only_offline_demo_and_generated_web_secret(self):
        for value in (
            "      - key: PERSONAL_AGENT_CONFIG\n        value: /app/course_demo/config.json",
            "      - key: PERSONAL_AGENT_DEMO_MODE\n        value: \"1\"",
            "      - key: PERSONAL_AGENT_DEMO_DATA_ROOT\n        value: /app/course_demo",
            "      - key: PERSONAL_AGENT_HTTPS\n        value: \"1\"",
            "      - key: PERSONAL_AGENT_WEB_SECRET\n        generateValue: true",
        ):
            self.assertIn(value, self.blueprint_text)
        self.assertNotRegex(
            self.blueprint_text,
            r"(?i)(api[_-]?key|password|access[_-]?token):\s*\S+",
        )

    def test_render_port_is_used_when_project_specific_port_is_absent(self):
        with patch.dict(
            "os.environ",
            {"PORT": "10000"},
            clear=True,
        ):
            arguments = build_parser().parse_args([])
        self.assertEqual(arguments.host, "0.0.0.0")
        self.assertEqual(arguments.port, 10000)

    def test_project_specific_port_overrides_render_port(self):
        with patch.dict(
            "os.environ",
            {"PORT": "10000", "PERSONAL_AGENT_WEB_PORT": "9000"},
            clear=True,
        ):
            arguments = build_parser().parse_args([])
        self.assertEqual(arguments.port, 9000)

    def test_container_does_not_override_platform_port_and_healthcheck_is_dynamic(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("PERSONAL_AGENT_WEB_PORT=", dockerfile)
        self.assertIn("os.environ.get('PORT', '8000')", dockerfile)

    def test_public_demo_documentation_discloses_ephemeral_and_cold_start_limits(self):
        guide = (ROOT / "docs" / "course" / "RENDER_DEPLOYMENT_GUIDE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("15 分钟", guide)
        self.assertIn("临时文件系统", guide)
        self.assertIn("不得使用个人 Vault", guide)
        self.assertIn("尚未获得公开 URL", guide)


if __name__ == "__main__":
    unittest.main()
