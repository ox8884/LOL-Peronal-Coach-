"""CLI 진입점 회귀 테스트 — 오류 경로가 원시 traceback 대신 사용자 메시지를 낸다."""

import os
import subprocess
import sys
import tempfile


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


def test_export_directory_out_gives_friendly_error_not_traceback() -> None:
    """--out 에 디렉터리를 넘기면 ClickException 문구가 나오고 traceback은 없다."""
    from click.testing import CliRunner

    from lol_coach.cli import export_cmd

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.invoke(export_cmd, ["--count", "3", "--out", tmp])
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "디렉터리" in result.output
