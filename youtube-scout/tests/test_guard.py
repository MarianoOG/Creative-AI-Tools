import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / "scripts" / "guard.py"
sys.path.insert(0, str(GUARD.parent))
import guard  # noqa: E402


@pytest.mark.parametrize("name", [
    "youtube-scout/brand.txt", "youtube-scout/config.toml", "youtube-scout/.env",
    "youtube-scout/keywords.generated.txt", "youtube-scout/out/2026-11-11.json", "youtube-scout/state/run.json",
])
def test_local_data_is_blocked(name):
    assert guard.problems(name)


def test_secrets_and_emails_are_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "youtube-scout").mkdir()
    key = "youtube-scout/a.py"
    (tmp_path / key).write_text('KEY = "AIza' + "aB3" * 11 + "Q9" + '"\n')
    assert any("Google API key" in p for p in guard.problems(key))
    (tmp_path / key).write_text("contact: someone" + "@example.com\n")
    assert any("email" in p for p in guard.problems(key))
    (tmp_path / key).write_text("print('fine')\n")
    assert guard.problems(key) == []


def test_tracked_files_are_clean():
    """The release check: nothing committed holds a key, an email or local data."""
    try:
        subprocess.run(["git", "rev-parse"], check=True, capture_output=True, cwd=GUARD.parent)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    result = subprocess.run([sys.executable, str(GUARD), "--tracked"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
