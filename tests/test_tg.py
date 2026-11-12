"""TelegramHelper unit test: fetch builds a runnable command.

Run from the repo root: python3 tests/test_tg.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpl.tg import TelegramError, TelegramHelper


def test_fetch_command_points_at_real_files():
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        out = Path.home() / ".hermes" / "cache" / "scratch" / "tg-test.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"chats": []}), encoding="utf-8")
        return FakeProc()

    real_run = subprocess.run
    subprocess.run = fake_run
    try:
        tg = TelegramHelper(REPO_ROOT, handler_timeout=5.0)
        # Point env discovery at a temp file so no real session is touched.
        tg._env_searched = True
        tg._env_file = Path(tempfile.gettempdir()) / "jpl-test.env"
        tg._env_file.write_text("X=1", encoding="utf-8")
        data = tg.fetch(scratch_name="tg-test.json", max_chats=1, limit=1)
    finally:
        subprocess.run = real_run
    assert data == {"chats": [], "_elapsed_s": data["_elapsed_s"]}
    exe, script = seen["cmd"][0], seen["cmd"][1]
    # The bug this guards: passing a bound method instead of the script path.
    assert script.endswith(".py") and "bound method" not in script, script
    assert Path(script).is_file(), script


REPO_ROOT = str(Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    test_fetch_command_points_at_real_files()
    print("OK: tg")
