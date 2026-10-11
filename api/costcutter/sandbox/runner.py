"""Run agent code in Docker: an install step with the package registry, a run step with only the proxy.

Dependencies go into a named volume in the install step and are mounted
read-only in the run step, so the run step needs no network beyond the proxy
and the agent's directory is never written to.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / "sandbox" / "python.Dockerfile"
NODE_DOCKERFILE = REPO_ROOT / "sandbox" / "node.Dockerfile"
IMAGES = {"python": ("whittle-sandbox-python", DOCKERFILE), "node": ("whittle-sandbox-node", NODE_DOCKERFILE)}


def image_tag(kind: str) -> str:
    """The sandbox image for a kind of project, named by the contents of its Dockerfile.

    The tag used to be fixed (":local") and the image was built only when it was missing, so a
    machine that already had one kept it for ever: the live server went on installing with the
    old package manager after the Dockerfile was changed. A tag made from the file's hash means
    a changed Dockerfile is a different image, and it is built the first time it is needed."""
    name, dockerfile = IMAGES[kind]
    return f"{name}:{hashlib.sha256(dockerfile.read_bytes()).hexdigest()[:12]}"
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
        """Kept for the tests; ensure_image("python") is the general form."""
        if not DOCKERFILE.is_file():
            raise FileNotFoundError(f"missing Dockerfile at {DOCKERFILE}")
        subprocess.run(
            [self._docker, "build", "-q", "-t", image_tag("python"), "-f", str(DOCKERFILE), str(REPO_ROOT / "sandbox")],
            check=True,
            capture_output=True,
            text=True,
        )

    def ensure_image(self, kind: str) -> str:
        """Build the sandbox image for a kind of project if it is not there yet. Returns its tag."""
        image, dockerfile = image_tag(kind), IMAGES[kind][1]
        have = subprocess.run([self._docker, "image", "inspect", image], capture_output=True)
        if have.returncode != 0:
            subprocess.run([self._docker, "build", "-q", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)], check=True, capture_output=True, text=True, timeout=900)
        return image

    def ensure_internal_network(self) -> None:
        networks = subprocess.run([self._docker, "network", "ls", "--format", "{{.Name}}"], capture_output=True, text=True).stdout.split()
        if INTERNAL_NETWORK not in networks:
            subprocess.run([self._docker, "network", "create", "--internal", INTERNAL_NETWORK], check=True, capture_output=True)

    def ensure_relay(self, host_port: int, name: str = RELAY) -> str:
        """An internal network where the agent can reach one thing: a relay to the proxy on the host.

        The agent container joins only the internal network, which Docker keeps off the
        internet. The relay container sits on that network and on the default bridge, and
        forwards one port to the proxy. Returns the base URL the agent should use."""
        self.ensure_internal_network()
        running = subprocess.run([self._docker, "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}} {{.Label \"whittle.port\"}}"], capture_output=True, text=True).stdout.strip()
        if running != f"{name} {host_port}":
            subprocess.run([self._docker, "rm", "-f", name], capture_output=True)
            subprocess.run(
                [self._docker, "run", "-d", "--name", name, "--label", f"whittle.port={host_port}", "--restart", "unless-stopped",
                 "--network", INTERNAL_NETWORK, "--add-host", "host.docker.internal:host-gateway",
                 RELAY_IMAGE, f"tcp-listen:{RELAY_PORT},fork,reuseaddr", f"tcp:host.docker.internal:{host_port}"],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([self._docker, "network", "connect", "bridge", name], check=True, capture_output=True)
        return f"http://{name}:{RELAY_PORT}"

    @staticmethod
    def deps_volume(job_id: str) -> str:
        return f"whittle-deps-{job_id}"

    @staticmethod
    def python_requirements(project: Path) -> tuple[list[str], str]:
        """The pip arguments that install a Python project's dependencies, and where they came from."""
        if (project / "requirements.txt").is_file():
            return ["-r", "requirements.txt"], "requirements.txt"
        pyproject = project / "pyproject.toml"
        if pyproject.is_file():
            import tomllib

            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
            deps = list((data.get("project") or {}).get("dependencies") or [])
            poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            for name, spec in poetry.items():
                if name.lower() != "python":
                    deps.append(name if not isinstance(spec, str) or spec in ("*", "") else f"{name}{spec if spec[0] in '<>=!~' else '==' + spec.lstrip('^~')}")
            if deps:
                return deps, "pyproject.toml"
        return [], ""

    @staticmethod
    def node_install_command(project: Path) -> tuple[list[str], str]:
        """The command that installs a JavaScript project's dependencies, by its lockfile."""
        common = ["--ignore-scripts"]  # a stranger's install scripts do not run
        if (project / "pnpm-lock.yaml").is_file():
            return ["pnpm", "install", "--frozen-lockfile", "--prod=false", "--store-dir", "node_modules/.pnpm-store", *common], "pnpm-lock.yaml"
        if (project / "yarn.lock").is_file():
            return ["yarn", "install", "--frozen-lockfile", "--production=false", "--cache-folder", "node_modules/.yarn-cache", *common], "yarn.lock"
        if (project / "package-lock.json").is_file():
            return ["npm", "ci", "--include=dev", "--cache", "node_modules/.npm-cache", *common], "package-lock.json"
        return ["npm", "install", "--include=dev", "--no-package-lock", "--cache", "node_modules/.npm-cache", *common], "package.json"

    def install(self, workdir: Path, job_id: str, *, kind: str = "python", subdir: str = "", timeout_s: int = 900) -> SandboxRunResult:
        """Install the project's dependencies into the job's dependency volume. This step has network; the run step does not."""
        project = (workdir / subdir).resolve()
        if kind == "node":
            if not (project / "package.json").is_file():
                return SandboxRunResult(0, "no package.json here; nothing to install\n", "", "")
            command, source = self.node_install_command(project)
            (project / "node_modules").mkdir(exist_ok=True)  # the mount point for the dependency volume
            # A new volume belongs to root; the sandbox user must be able to write the install into it.
            subprocess.run([self._docker, "run", "--rm", "--user", "0", "--network", "none", "-v", f"{self.deps_volume(job_id)}:/v", self.ensure_image(kind), "chown", "10001:10001", "/v"],
                           check=True, capture_output=True, text=True, timeout=120)
            result = self._run(workdir, command, network="bridge", extra_env={}, timeout_s=timeout_s, kind=kind, subdir=subdir,
                               deps_volume=self.deps_volume(job_id), deps_writable=True, pids=1024, tmp="1g")
            return SandboxRunResult(result.exit_code, f"installed from {source}\n" + result.stdout[-2000:], result.stderr, result.container_id)
        args, source = self.python_requirements(project)
        if not args:
            return SandboxRunResult(0, "no requirements.txt or pyproject.toml dependencies; nothing to install\n", "", "")
        result = self._run(workdir, ["pip", "install", "--quiet", "--target", "/deps", *args], network="bridge", extra_env={}, timeout_s=timeout_s,
                           kind=kind, subdir=subdir, deps_volume=self.deps_volume(job_id), deps_writable=True)
        return SandboxRunResult(result.exit_code, f"installed from {source}\n" + result.stdout[-2000:], result.stderr, result.container_id)

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
        kind: str = "python",
        subdir: str = "",
    ) -> SandboxRunResult:
        """Run step: the agent sees a dummy key and a base URL that lead to the proxy."""
        base = proxy_base_url.rstrip("/")
        # The owner's own variables go in first, so a key or address of theirs can never replace the proxy's.
        env = dict(extra_env or {})
        if provider in ("openai", "any"):
            env.update({"OPENAI_BASE_URL": base + "/v1", "OPENAI_API_BASE": base + "/v1", "OPENAI_API_KEY": dummy_api_key})
        if provider in ("anthropic", "any"):  # "any": a dry run, before the code has shown which provider it calls
            env.update({"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": dummy_api_key})
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
            kind=kind,
            subdir=subdir,
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
        kind: str = "python",
        subdir: str = "",
        pids: int = 256,
        tmp: str = "256m",
    ) -> SandboxRunResult:
        workdir = workdir.resolve()
        if not workdir.is_dir():
            raise FileNotFoundError(workdir)
        project = (workdir / subdir).resolve()
        if project != workdir and workdir not in project.parents:
            raise ValueError("the working folder is outside the repository")
        inside = "/work" + ("/" + str(project.relative_to(workdir)) if project != workdir else "")
        image = self.ensure_image(kind)
        # Python dependencies live beside the code at /deps; JavaScript ones must be the project's node_modules.
        deps_at = f"{inside}/node_modules" if kind == "node" else "/deps"

        name = f"whittle-{uuid.uuid4().hex[:12]}"
        args = [
            self._docker, "run", "--rm", "--name", name,
            "--network", network,
            "--read-only",
            "--tmpfs", f"/tmp:rw,nosuid,size={tmp}",
            "--user", "10001:10001",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "2g",
            "--pids-limit", str(pids),
            "-v", f"{workdir}:/work:ro",
            "-w", inside,
        ]
        if deps_volume:
            args.extend(["-v", f"{deps_volume}:{deps_at}" + ("" if deps_writable else ":ro")])
        if allow_host_gateway:
            args.extend(["--add-host", "host.docker.internal:host-gateway"])
        for key, value in extra_env.items():
            args.extend(["-e", f"{key}={value}"])
        args.append(image)
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

    def proxy_url_for_container(self, host_port: int, path: str = "", relay_name: str = RELAY) -> str:
        """Base URL agents inside Docker use to reach the proxy on the host."""
        if os.environ.get("WHITTLE_SANDBOX_RUN_NETWORK", "internal") == "internal":
            return self.ensure_relay(host_port, relay_name) + path
        return f"http://host.docker.internal:{host_port}{path}"
