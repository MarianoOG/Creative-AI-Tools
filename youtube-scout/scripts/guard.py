#!/usr/bin/env python3
"""Pre-commit guard: block secrets and local data from being committed.

    python youtube-scout/scripts/guard.py FILE...     check the given files
    python youtube-scout/scripts/guard.py --tracked   check every git-tracked file

Fails on API-key-shaped strings anywhere, on email addresses inside the tool,
and on any niche input, config, output, state or cache file. Pair it with
gitleaks (see the repository's .pre-commit-config.yaml) for broader coverage.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Anthropic API key": re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}"),
    "OpenAI API key": re.compile(r"sk-(proj-)?[0-9A-Za-z]{32,}"),
    "Google OAuth secret": re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "key assignment": re.compile(
        r"(?i)\b[A-Z_]*(API_KEY|SECRET|TOKEN)\s*=\s*['\"]?[0-9A-Za-z_\-]{20,}"
    ),
}
PLACEHOLDER = re.compile(r"(?i)your|example|here|xxxx|placeholder|dummy|changeme")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

TOOL = "youtube-scout"
FORBIDDEN_NAMES = {"brand.txt", "keywords.generated.txt", "config.toml", ".env"}
FORBIDDEN_DIRS = {"out", "state", "cache"}
EMAIL_ALLOWED = {f"{TOOL}/scripts/guard.py"}


def problems(path: str) -> list[str]:
    found = []
    parts = PurePosixPath(path).parts
    if parts and parts[0] == TOOL:
        if parts[-1] in FORBIDDEN_NAMES or (parts[-1].startswith("exclude") and parts[-1].endswith(".txt")):
            found.append("local niche input, config or keys: never commit it")
        if FORBIDDEN_DIRS & set(parts[1:-1]):
            found.append("local output/state/cache data: never commit it")
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return found
    for name, pattern in SECRET_PATTERNS.items():
        if any(not PLACEHOLDER.search(match.group(0)) for match in pattern.finditer(text)):
            found.append(f"looks like it contains a {name}")
    if parts and parts[0] == TOOL and path not in EMAIL_ALLOWED and EMAIL.search(text):
        found.append("contains an email address (the tool never collects or stores emails)")
    return found


def main(argv: list[str]) -> int:
    if argv[:1] == ["--tracked"]:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True,
                               cwd=root.stdout.strip()).stdout.split()
        os.chdir(root.stdout.strip())
    else:
        files = argv
    failed = False
    for path in files:
        for problem in problems(path):
            print(f"{path}: {problem}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
