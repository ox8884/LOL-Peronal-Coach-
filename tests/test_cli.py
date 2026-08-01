import os
import subprocess
import sys


def test_help_does_not_crash_on_windows_cp949_console() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp949:strict"

    result = subprocess.run(
        [sys.executable, "-m", "lol_coach", "--help"],
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr.decode("ascii", errors="backslashreplace")
