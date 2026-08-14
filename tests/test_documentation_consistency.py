import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = (
    "https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.1"
)


class DocumentationConsistencyTests(unittest.TestCase):
    def _read(self, relative_path: str) -> str:
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"missing documentation: {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_primary_readme_matches_current_release_and_runtime(self):
        document = self._read("README.md")
        self.assertIn(RELEASE_URL, document)
        self.assertIn("228", document)
        self.assertIn("Flask", document)
        self.assertIn("keyring", document)
        self.assertIn("Waitress", document)
        self.assertNotIn("项目当前只依赖 Python 3.9+ 标准库", document)
        self.assertNotIn("模型凭据应由未来的 Provider Adapter", document)

    def test_status_and_plan_describe_executed_delivery(self):
        status = self._read("docs/PROJECT_STATUS.md")
        plan = self._read("PLAN.md")
        self.assertIn("v0.1.1", status)
        self.assertIn("228", status)
        self.assertIn("### T14", plan)
        self.assertIn("状态：`DONE`", plan[plan.index("### T14") :])
        self.assertIn("### T15", plan)
        self.assertIn("状态：`IN PROGRESS`", plan[plan.index("### T15") :])

    def test_documentation_index_and_release_evidence_exist(self):
        index = self._read("docs/DOCUMENTATION_INDEX.md")
        evidence = self._read("docs/course/GITHUB_RELEASE_EVIDENCE_v2.md")
        self.assertIn("历史快照", index)
        self.assertIn("测试语料", index)
        self.assertIn(RELEASE_URL, evidence)
        self.assertIn("v0.1.1", evidence)

    def test_reflection_is_based_on_student_draft_and_discloses_assistance(self):
        guide = self._read("REFLECTION_GUIDE.md")
        reflection = self._read("REFLECTION.md")
        self.assertIn("必须由学生本人", guide)
        self.assertIn("本文观点、经历和初稿由本人提供", reflection)
        self.assertIn("AI 根据初稿进行了", reflection)
        self.assertFalse((ROOT / "REFLECTION_WORKSHEET.md").exists())


if __name__ == "__main__":
    unittest.main()
