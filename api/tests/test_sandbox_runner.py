"""Sandbox runner unit tests (Docker optional)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from costcutter.sandbox.runner import SandboxRunner


def docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info"],
        capture_output=True,
    ).returncode == 0


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_install_step_can_run_python(tmp_path):
    runner = SandboxRunner()
    runner.ensure_python_image()
    script = tmp_path / "hi.py"
    script.write_text('print("sandbox-ok")', encoding="utf-8")
    result = runner.run_install(tmp_path, ["python", "hi.py"])
    assert result.exit_code == 0
    assert "sandbox-ok" in result.stdout


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_run_step_with_no_network_cannot_curl(tmp_path):
    runner = SandboxRunner()
    runner.ensure_python_image()
    result = runner._run(
        tmp_path,
        ["python", "-c", "import urllib.request; urllib.request.urlopen('http://example.com', timeout=3)"],
        network="none",
        extra_env={},
        timeout_s=60,
    )
    assert result.exit_code != 0
