import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CourseHandoffContractTests(unittest.TestCase):
    def _read(self, relative_path: str) -> str:
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"missing course handoff file: {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_course_readme_has_required_entry_sections_and_safe_commands(self):
        document = self._read("README_COURSE.md")
        for heading in (
            "## 项目简介",
            "## 安装",
            "## 运行与演示",
            "## 分发",
            "## 目录结构",
            "## 凭据与安全边界",
            "## 测试与验收",
            "## 已知限制与未完成项",
        ):
            self.assertIn(heading, document)
        self.assertIn("python scripts/verify.py", document)
        self.assertIn("127.0.0.1:8000", document)
        self.assertNotIn("sk-", document)

    def test_architecture_covers_components_data_flow_and_trust_boundaries(self):
        document = self._read("docs/course/ARCHITECTURE.md")
        for heading in (
            "## 定位与边界",
            "## 组件架构",
            "## 核心数据流",
            "## 数据模型与持久化",
            "## 信任边界与安全控制",
            "## 部署架构",
        ):
            self.assertIn(heading, document)
        self.assertIn("```mermaid", document)
        self.assertIn("WebApplicationPort", document)

    def test_reflection_guide_requires_student_authorship_and_all_prompts(self):
        document = self._read("REFLECTION_GUIDE.md")
        self.assertIn("1500–2500", document)
        self.assertIn("必须由学生本人", document)
        for topic in (
            "Superpowers",
            "TDD",
            "subagent",
            "SPEC / PLAN",
            "prompt / context",
            "凭据与分发",
            "如果重做",
        ):
            self.assertIn(topic, document)


if __name__ == "__main__":
    unittest.main()
