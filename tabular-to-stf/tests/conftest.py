import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
FIXTURES = SKILL / "tests/fixtures"

sys.path.insert(0, str(SKILL / "scripts"))


def run_cli(*args, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SKILL / "scripts/stf.py"), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
