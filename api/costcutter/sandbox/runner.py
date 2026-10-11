"""Run agent code in Docker: an install step with the package registry, a run step with only the proxy.

Dependencies go into a named volume in the install step and are mounted
read-only in the run step, so the run step needs no network beyond the proxy
and the agent's directory is never written to.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_IMAGE = "whittle-sandbox-python:local"
DOCKERFILE = REPO_ROOT / "sandbox" / "python.Dockerfile"
INTERNAL_NETWORK = "whittle-internal"
RELAY = "whittle-relay"
RELAY_IMAGE = "alpine/socat:1.8.0.0"
RELAY_PORT = 8787


@dataclass(frozen=True)
class SandboxRunResult:
    exit_code: int
    stdout: str
    stderr: str
    container_id: str


class SandboxRunner:
    """Thin wrapper around `docker run` for the hackathon sandbox rules."""

    def __init__(self, *, docker_bin: str = "docker") -> None:
        self._docker = docker_bin

    def ensure_python_image(self) -> None:
        if not DOCKERFILE.is_file():
            raise FileNotFoundError(f"missing Dockerfile at {DOCKERFILE}")
        subprocess.run(
            [self._docker, "build", "-q", "-t", PYTHON_IMAGE, "-f", str(DOCKERFILE), str(REPO_ROOT / "sandbox")],
            check=True,
            capture_output=True,
            text=True,
        )

    def ensure_internal_network(self) -> None:
        networks = subprocess.run([self._docker, "network", "ls", "--format", "{{.Name}}"], capture_output=True, text=True).stdout.split()
        if INTERNAL_NETWORK not in networks:
            subprocess.run([self._docker, "network", "create", "--internal", INTERNAL_NETWORK], check=True, capture_output=True)

    def ensure_relay(self, host_port: int) -> str:
        """An internal network where the agent can reach one thing: a relay to the proxy on the host.

        The agent container joins only the internal network, which Docker keeps off the
        internet. The relay container sits on that network and on the default bridge, and
        forwards one port to the proxy. Returns the base URL the agent should use."""
        self.ensure_internal_network()
        running = subprocess.run([self._docker, "ps", "--filter", f"name=^{RELAY}$", "--format", "{{.Names}} {{.Label \"whittle.port\"}}"], capture_output=True, text=True).stdout.strip()
        if running != f"{RELAY} {host_port}":
            subprocess.run([self._docker, "rm", "-f", RELAY], capture_output=True)
            subprocess.run(
                [self._docker, "run", "-d", "--name", RELAY, "--label", f"whittle.port={host_port}", "--restart", "unless-stopped",
                 "--network", INTERNAL_NETWORK, "--add-host", "host.docker.internal:host-gateway",
                 RELAY_IMAGE, f"tcp-listen:{RELAY_PORT},fork,reuseaddr", f"tcp:host.docker.internal:{host_port}"],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([self._docker, "network", "connect", "bridge", RELAY], check=True, capture_output=True)
        return f"http://{RELAY}:{RELAY_PORT}"

    @staticmethod
    def deps_volume(job_id: str) -> str:
        return f"whittle-deps-{job_id}"

    def install(self, workdir: Path, job_id: str, *, timeout_s: int = 600) -> SandboxRunResult:
        """Install the agent's requirements.txt into the job's dependency volume. Network: registries only."""
        req = workdir / "requirements.txt"
        if not req.is_file():
            return SandboxRunResult(0, "no requirements.txt; nothing to install\n", "", "")
        return self._run(
            workdir,
            ["pip", "install", "--quiet", "--target", "/deps", "-r", "requirements.txt"],
            network="bridge",
            extra_env={},
            timeout_s=timeout_s,
            deps_volume=self.deps_volume(job_id),
            deps_writable=True,
        )

    def run_agent(
        self,
        workdir: Path,
        command: Sequence[str],
        *,
        job_id: str,
        proxy_base_url: str,
        dummy_api_key: str,
        provider: str = "anthropic",
        extra_env: dict[str, str] | None = None,
        timeout_s: int = 900,
    ) -> SandboxRunResult:
        """Run step: the agent sees a dummy key and a base URL that lead to the proxy."""
        base = proxy_base_url.rstrip("/")
        env = {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": dummy_api_key}
        if provider == "openai":
            env = {"OPENAI_BASE_URL": base + "/v1", "OPENAI_API_KEY": dummy_api_key}
        env.update(extra_env or {})
        # "internal" (the default) lets the agent reach the proxy and nothing else.
        run_network = os.environ.get("WHITTLE_SANDBOX_RUN_NETWORK", "internal")
        if run_network == "internal":
            run_network = INTERNAL_NETWORK
            self.ensure_internal_network()
        return self._run(
            workdir,
            list(command),
            network=run_network,
            extra_env=env,
            timeout_s=timeout_s,
            allow_host_gateway=run_network != INTERNAL_NETWORK,
            deps_volume=self.deps_volume(job_id),
        )

    def remove_deps(self, job_id: str) -> None:
        subprocess.run([self._docker, "volume", "rm", "-f", self.deps_volume(job_id)], capture_output=True)

    def _run(
        self,
        workdir: Path,
        command: list[str],
        *,
        network: str,
        extra_env: dict[str, str],
        timeout_s: int,
        allow_host_gateway: bool = False,
        deps_volume: str | None = None,
        deps_writable: bool = False,
    ) -> SandboxRunResult:
        workdir = workdir.resolve()
        if not workdir.is_dir():
            raise FileNotFoundError(workdir)

        name = f"whittle-{uuid.uuid4().hex[:12]}"
        args = [
            self._docker, "run", "--rm", "--name", name,
            "--network", network,
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
            "--user", "10001:10001",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "2g",
            "--pids-limit", "128",
            "-v", f"{workdir}:/work:ro",
            "-w", "/work",
        ]
        if deps_volume:
            args.extend(["-v", f"{deps_volume}:/deps" + ("" if deps_writable else ":ro")])
        if allow_host_gateway:
            args.extend(["--add-host", "host.docker.internal:host-gateway"])
        for key, value in extra_env.items():
            args.extend(["-e", f"{key}={value}"])
        args.append(PYTHON_IMAGE)
        args.extend(command)

        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout_s,
                env={**os.environ, "DOCKER_CLI_HINTS": "false"},
            )
        except subprocess.TimeoutExpired as exc:
            subprocess.run([self._docker, "rm", "-f", name], capture_output=True)
            return SandboxRunResult(124, (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                                    f"timed out after {timeout_s}s", name)
        return SandboxRunResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, container_id=name)

    def proxy_url_for_container(self, host_port: int, path: str = "") -> str:
        """Base URL agents inside Docker use to reach the proxy on the host."""
        if os.environ.get("WHITTLE_SANDBOX_RUN_NETWORK", "internal") == "internal":
            return self.ensure_relay(host_port) + path
        return f"http://host.docker.internal:{host_port}{path}"
