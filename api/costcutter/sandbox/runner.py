"""Run agent code in Docker with network policy: install vs proxy-only run."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_IMAGE = "whittle-sandbox-python:local"
DOCKERFILE = REPO_ROOT / "sandbox" / "python.Dockerfile"


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
            [
                self._docker,
                "build",
                "-t",
                PYTHON_IMAGE,
                "-f",
                str(DOCKERFILE),
                str(REPO_ROOT / "sandbox"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def run_install(
        self,
        workdir: Path,
        command: Sequence[str],
        *,
        timeout_s: int = 600,
    ) -> SandboxRunResult:
        """Install step: outbound network allowed (package registries). No secrets in env."""
        return self._run(
            workdir,
            list(command),
            network="bridge",
            extra_env={},
            timeout_s=timeout_s,
        )

    def run_agent(
        self,
        workdir: Path,
        command: Sequence[str],
        *,
        proxy_base_url: str,
        dummy_api_key: str = "whittle-sandbox-dummy",
        provider: str = "anthropic",
        timeout_s: int = 900,
    ) -> SandboxRunResult:
        """Run step: only the host proxy is reachable; dummy model key in the container."""
        env = {
            "ANTHROPIC_BASE_URL": proxy_base_url.rstrip("/"),
            "ANTHROPIC_API_KEY": dummy_api_key,
        }
        if provider == "openai":
            env = {
                "OPENAI_BASE_URL": proxy_base_url.rstrip("/"),
                "OPENAI_API_KEY": dummy_api_key,
            }
        run_network = os.environ.get("WHITTLE_SANDBOX_RUN_NETWORK", "bridge")
        return self._run(
            workdir,
            list(command),
            network=run_network,
            extra_env=env,
            timeout_s=timeout_s,
            allow_host_gateway=True,
        )

    def _run(
        self,
        workdir: Path,
        command: list[str],
        *,
        network: str,
        extra_env: dict[str, str],
        timeout_s: int,
        allow_host_gateway: bool = False,
    ) -> SandboxRunResult:
        workdir = workdir.resolve()
        if not workdir.is_dir():
            raise FileNotFoundError(workdir)

        name = f"whittle-{uuid.uuid4().hex[:12]}"
        args = [
            self._docker,
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            network,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--user",
            "10001:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "2g",
            "--pids-limit",
            "128",
            "-v",
            f"{workdir}:/work:ro",
            "-w",
            "/work",
        ]
        if allow_host_gateway:
            args.extend(["--add-host", "host.docker.internal:host-gateway"])
        for key, value in extra_env.items():
            args.extend(["-e", f"{key}={value}"])
        args.append(PYTHON_IMAGE)
        args.extend(command)

        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "DOCKER_CLI_HINTS": "false"},
        )
        return SandboxRunResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            container_id=name,
        )

    @staticmethod
    def proxy_url_for_container(host_port: int = 8790) -> str:
        """Base URL agents inside Docker use to reach the proxy on the host."""
        return f"http://host.docker.internal:{host_port}"
