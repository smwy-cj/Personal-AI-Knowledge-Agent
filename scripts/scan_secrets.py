"""Dependency-free high-confidence secret scan for working tree and Git history."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
TEXT_LIMIT = 2 * 1024 * 1024
SKIP_PARTS = {".git", ".venv", "__pycache__", "build", "data", "dist", ".pytest_cache"}
SKIP_SUFFIXES = {".db", ".gif", ".ico", ".jpeg", ".jpg", ".pdf", ".png", ".pyc", ".sqlite", ".sqlite3", ".whl", ".zip"}
RULES: Sequence[Tuple[str, re.Pattern[str]]] = (
    ("openai_api_key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{40,}(?![A-Za-z0-9])")),
    ("github_personal_access_token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,}(?![A-Za-z0-9])")),
    ("gitlab_personal_access_token", re.compile(r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9])")),
    ("aws_access_key_id", re.compile(r"(?<![A-Z0-9])(AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential_url", re.compile(r"https?://[^\s/:@]{1,64}:[^\s/@]{12,}@[^\s/]+")),
)


def scan_text(path: str, text: str, source: str) -> List[Dict[str, object]]:
    findings: List[Dict[str, object]] = []
    for rule, pattern in RULES:
        for match in pattern.finditer(text):
            value = match.group(0)
            findings.append({
                "source": source,
                "path": path,
                "line": text.count("\n", 0, match.start()) + 1,
                "rule": rule,
                "fingerprint": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
            })
    return findings


def scan_working_tree(root: Path = ROOT) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.suffix.casefold() in SKIP_SUFFIXES or path.stat().st_size > TEXT_LIMIT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        output.extend(scan_text(relative.as_posix(), text, "working-tree"))
    return output


def scan_git_history(root: Path = ROOT) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    seen_blobs = set()
    for revision in _git(root, "rev-list", "--all").splitlines():
        for line in _git(root, "ls-tree", "-r", revision).splitlines():
            try:
                metadata, path = line.split("\t", 1)
                _, object_type, object_id = metadata.split()
            except ValueError:
                continue
            if object_type != "blob" or object_id in seen_blobs:
                continue
            seen_blobs.add(object_id)
            size_text = _git(root, "cat-file", "-s", object_id).strip()
            if not size_text.isdigit() or int(size_text) > TEXT_LIMIT:
                continue
            document = subprocess.run(
                ["git", "cat-file", "blob", object_id], cwd=str(root), check=True, stdout=subprocess.PIPE
            ).stdout
            try:
                text = document.decode("utf-8")
            except UnicodeDecodeError:
                continue
            output.extend(scan_text("%s:%s" % (revision[:12], path), text, "git-history"))
    return output


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return result.stdout.decode("utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--working-tree", action="store_true")
    parser.add_argument("--git-history", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Iterable[str] = ()) -> int:
    arguments = build_parser().parse_args(list(argv) or None)
    scan_tree = arguments.working_tree or not arguments.git_history
    findings = scan_working_tree() if scan_tree else []
    if arguments.git_history:
        findings.extend(scan_git_history())
    scopes = [scope for enabled, scope in ((scan_tree, "working-tree"), (arguments.git_history, "git-history")) if enabled]
    report = {"schema": "secret_scan_v1", "scopes": scopes, "finding_count": len(findings), "findings": findings}
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print("secret scan: %s finding(s) across %s" % (len(findings), ", ".join(scopes)))
        for item in findings:
            print("{source} {path}:{line} {rule} fingerprint={fingerprint}".format(**item))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
