"""Sanitized repository privacy/secret scan (1.0-beta acceptance gate).

Spine Former Program 11 requires "a sanitized repository scan for credentials,
PII, private paths, and raw Canvas responses" as a release-acceptance step. This
test is that scan, run inside the suite: it walks every *tracked* file and fails
if a high-signal secret, a real (non-synthetic) email address, or a personal
machine home path is committed.

Design: high signal, near-zero false positive. It intentionally does NOT try to
detect "raw Canvas responses" heuristically (that is enforced structurally by the
per-schema allowlist tests in test_course_catalog.py / test_mirror_store.py /
test_course_info_routes.py, which assert normalizers keep only allowlisted fields
and never persist tokens, signed URLs, emails, or raw error text). This scan is the
credentials/PII/private-path backstop for the *committed tree*, complementing the
`.githooks/pre-commit` token backstop with a suite-enforced gate.

If this test fails, a secret or PII value was committed — remove it and rotate it.
To exempt a genuinely benign match (a placeholder, a synthetic fixture), add it to
the ALLOWLIST_SUBSTRINGS set with a comment, never by weakening a pattern.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF_NAME = Path(__file__).name

# Extensions we never scan as text (binary / generated). Everything else tracked
# is scanned; a decode failure is skipped defensively.
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".docx", ".xlsx",
    ".pptx", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webp", ".db", ".pyc",
}

# --- high-signal secret patterns -------------------------------------------------
CANVAS_TOKEN = re.compile(r"\b\d{3,6}~[A-Za-z0-9]{40,}\b")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")
CLOUD_SECRET = re.compile(
    r"\bAKIA[0-9A-Z]{16}\b"          # AWS access key id
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}\b"  # Slack token
    r"|\bsk-[A-Za-z0-9]{32,}\b"      # OpenAI/OpenRouter-style secret key
)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Personal machine home path with a concrete username in the first segment.
HOME_PATH = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|/home/)([A-Za-z0-9._-]+)")

# Synthetic/placeholder values that are safe by construction.
ALLOWLIST_SUBSTRINGS = {
    "@anthropic.com",   # co-author trailer domain, never a real student
}
# Email domains that are synthetic by RFC/convention.
SAFE_EMAIL_DOMAINS = ("example.invalid", "example.com", "example.org", "example.net", "localhost")
# Username segments that are generic placeholders, not a real person's home dir.
SAFE_PATH_USERS = {"you", "user", "username", "name", "someone", "public", "runner", "<user>"}


def _tracked_text_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        if Path(rel).name == SELF_NAME:
            continue  # never scan this file's own pattern literals
        if Path(rel).suffix.lower() in BINARY_EXTS:
            continue
        yield rel


def _email_is_synthetic(match: str) -> bool:
    lower = match.lower()
    if any(sub in lower for sub in ALLOWLIST_SUBSTRINGS):
        return True
    domain = lower.rsplit("@", 1)[-1]
    return domain.endswith(SAFE_EMAIL_DOMAINS) or "example" in domain


def _path_user_is_placeholder(user: str) -> bool:
    return user.lower() in SAFE_PATH_USERS


def test_repository_is_free_of_secrets_pii_and_private_paths():
    findings: list[str] = []
    for rel in _tracked_text_files():
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, pat in (("canvas_token", CANVAS_TOKEN), ("jwt", JWT),
                              ("private_key", PRIVATE_KEY), ("cloud_secret", CLOUD_SECRET)):
                if pat.search(line):
                    findings.append(f"{rel}:{lineno} [{kind}]")
            for m in EMAIL.finditer(line):
                if not _email_is_synthetic(m.group(0)):
                    findings.append(f"{rel}:{lineno} [email] {m.group(0)}")
            for m in HOME_PATH.finditer(line):
                if not _path_user_is_placeholder(m.group(1)):
                    findings.append(f"{rel}:{lineno} [home_path] {m.group(0)}")
    assert not findings, (
        "Committed secret / PII / private-path value(s) found — remove and rotate:\n"
        + "\n".join(findings)
    )
