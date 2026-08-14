import unittest

from scripts.scan_secrets import scan_text


class SecretScannerTests(unittest.TestCase):
    def test_detects_high_confidence_tokens_private_keys_and_credential_urls(self):
        samples = {
            "openai_api_key": "sk-" + "A1b2" * 12,
            "github_personal_access_token": "ghp_" + "a1B2" * 10,
            "private_key": "-----BEGIN " + "PRIVATE KEY-----\nmaterial",
            "credential_url": "https://student:" + "super-secret-value@example.com/api",
        }
        for expected, value in samples.items():
            with self.subTest(expected=expected):
                findings = scan_text("sample.txt", value, "working-tree")
                self.assertIn(expected, {item["rule"] for item in findings})

    def test_ignores_documented_prefixes_and_explicit_placeholders(self):
        text = "\n".join(
            [
                "sk-",
                "ghp_",
                "PERSONAL_AGENT_WEB_SECRET=replace-with-a-long-random-value",
                "api_key=your-api-key-here",
                "password=<set-in-dashboard>",
            ]
        )
        self.assertEqual(scan_text("example.txt", text, "working-tree"), [])

    def test_finding_never_contains_secret_value(self):
        marker = "ghp_" + "xY9z" * 10
        finding = scan_text("sample.txt", marker, "working-tree")[0]
        self.assertNotIn(marker, repr(finding))
        self.assertIn("fingerprint", finding)


if __name__ == "__main__":
    unittest.main()
