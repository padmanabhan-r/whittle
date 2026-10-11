"""Sandbox runner: install into a volume with network, run without network beyond the proxy."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

from costcutter.sandbox.runner import SandboxRunner


def make_tmp_path_container_traversable(path: Path) -> None:
    if os.name != "posix":
        return

    path.chmod(0o755)
    temp_root = Path(tempfile.gettempdir())
    for parent in path.parents:
        if parent == temp_root:
            break
        parent.chmod(stat.S_IMODE(parent.stat().st_mode) | stat.S_IXOTH)


def docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not docker_available(), reason="docker not available")


@pytest.fixture(scope="module")
def runner():
    r = SandboxRunner()
    r.ensure_python_image()
    return r


def test_install_then_run_uses_the_deps_volume(runner, tmp_path):
    make_tmp_path_container_traversable(tmp_path)
    job = "test-" + uuid.uuid4().hex[:8]
    (tmp_path / "requirements.txt").write_text("six==1.16.0\n")
    (tmp_path / "main.py").write_text("import six, os; print('six', six.__version__, os.environ.get('ANTHROPIC_API_KEY'))\n")
    try:
        installed = runner.install(tmp_path, job)
        assert installed.exit_code == 0, installed.stderr
        result = runner.run_agent(tmp_path, ["python", "main.py"], job_id=job, proxy_base_url="http://host.docker.internal:1", dummy_api_key="whittle-abc")
        assert result.exit_code == 0, result.stderr
        assert "six 1.16.0 whittle-abc" in result.stdout
    finally:
        runner.remove_deps(job)


def test_run_step_cannot_write_the_agent_dir(runner, tmp_path):
    make_tmp_path_container_traversable(tmp_path)
    (tmp_path / "main.py").write_text("open('/work/x', 'w')\n")
    result = runner.run_agent(tmp_path, ["python", "main.py"], job_id="test-ro", proxy_base_url="http://host.docker.internal:1", dummy_api_key="whittle-abc")
    assert result.exit_code != 0


def test_no_network_cannot_reach_the_internet(runner, tmp_path):
    make_tmp_path_container_traversable(tmp_path)
    (tmp_path / "main.py").write_text("import urllib.request; urllib.request.urlopen('http://example.com', timeout=3)\n")
    result = runner._run(tmp_path, ["python", "main.py"], network="none", extra_env={}, timeout_s=60)
    assert result.exit_code != 0


def test_run_step_reaches_only_the_relay(runner, tmp_path, monkeypatch):
    """On the internal network the agent can open the relay and nothing on the internet."""
    make_tmp_path_container_traversable(tmp_path)
    monkeypatch.delenv("WHITTLE_SANDBOX_RUN_NETWORK", raising=False)
    # Its own relay, so the test never replaces the relay a running job is using.
    base = runner.proxy_url_for_container(1, relay_name="whittle-relay-test")  # a port nothing listens on: the relay accepts, the host refuses
    (tmp_path / "main.py").write_text(
        "import socket, sys\n"
        "ok = socket.create_connection(('whittle-relay-test', 8787), timeout=5)\n"
        "ok.close()\n"
        "try:\n"
        "    socket.create_connection(('example.com', 80), timeout=3)\n"
        "except OSError:\n"
        "    print('internet blocked'); sys.exit(0)\n"
        "print('internet reachable'); sys.exit(1)\n"
    )
    result = runner.run_agent(tmp_path, ["python", "main.py"], job_id="test-net", proxy_base_url=base, dummy_api_key="whittle-x")
    subprocess.run(["docker", "rm", "-f", "whittle-relay-test"], capture_output=True)
    assert result.exit_code == 0, result.stderr + result.stdout
    assert "internet blocked" in result.stdout
