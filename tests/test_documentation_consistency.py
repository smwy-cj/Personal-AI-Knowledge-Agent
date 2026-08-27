import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
RELEASE_URL = RELEASE["release_url"]


class DocumentationConsistencyTests(unittest.TestCase):
    def _read(self, relative_path: str) -> str:
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"missing documentation: {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_primary_readme_matches_current_release_and_runtime(self):
        document = self._read("README.md")
        self.assertIn(RELEASE_URL, document)
        self.assertIn(RELEASE["tag"], document)
        self.assertIn(RELEASE["commit"], document)
        self.assertIn(f'{RELEASE["acceptance_test_count"]} 项测试', document)
        self.assertIn("Flask", document)
        self.assertIn("keyring", document)
        self.assertIn("Waitress", document)
        self.assertNotIn("项目当前只依赖 Python 3.9+ 标准库", document)
        self.assertNotIn("模型凭据应由未来的 Provider Adapter", document)

    def test_status_and_plan_describe_executed_delivery(self):
        status = self._read("docs/PROJECT_STATUS.md")
        plan = self._read("PLAN.md")
        self.assertIn(RELEASE["tag"], status)
        self.assertIn(f'{RELEASE["acceptance_test_count"]} 项自动化测试', status)
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

    def test_release_metadata_matches_package_and_current_evidence(self):
        pyproject = self._read("pyproject.toml")
        version_match = re.search(
            r'^version\s*=\s*"([^"]+)"\s*$', pyproject, flags=re.MULTILINE
        )
        self.assertIsNotNone(version_match)
        self.assertEqual(RELEASE["version"], version_match.group(1))
        self.assertEqual(RELEASE["tag"], f'v{RELEASE["version"]}')

        course_readme = self._read("README_COURSE.md")
        release_notes = self._read(f'RELEASE_NOTES_{RELEASE["tag"]}.md')
        ci_evidence = self._read("docs/course/CI_CD_EVIDENCE_v2.md")
        expected_test_result = f'Ran {RELEASE["acceptance_test_count"]} tests'
        self.assertIn(expected_test_result, course_readme)
        self.assertIn(
            f'{RELEASE["acceptance_test_count"]} 项自动化测试', release_notes
        )
        self.assertIn(RELEASE["commit"], ci_evidence)

    def test_release_metadata_matches_local_git_tag_when_available(self):
        try:
            tagged_commit = subprocess.run(
                ["git", "rev-parse", f'{RELEASE["tag"]}^{{commit}}'],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.skipTest("release tag is unavailable in this source checkout")
        self.assertEqual(RELEASE["commit"], tagged_commit)

    def test_reflection_is_based_on_student_draft_and_discloses_assistance(self):
        guide = self._read("REFLECTION_GUIDE.md")
        reflection = self._read("REFLECTION.md")
        self.assertIn("必须由学生本人", guide)
        self.assertIn("本文观点、经历和初稿由本人提供", reflection)
        self.assertIn("AI 根据初稿进行了", reflection)
        self.assertFalse((ROOT / "REFLECTION_WORKSHEET.md").exists())


if __name__ == "__main__":
    unittest.main()
