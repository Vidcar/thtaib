"""Managed-process helpers. Connected endpoints never use this supervisor.

Issue #62: destructive actions require a persisted process identity
(pid + create_time + executable). A healthy HTTP endpoint alone is not
ownership. Stale or reused PIDs are refused before terminate/kill.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Any, Literal

import httpx
import psutil

from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.process_logs import RotatingLogWriter, pump_stream_to_log
from workbench_backend.inference.schemas import (
    HealthReport,
    ProcessIdentity,
    ResourceUsage,
    ServerProperties,
)

IdentityVerdict = Literal["match", "mismatch", "gone"]

CREATE_TIME_TOLERANCE_SECONDS = 0.05

# Honest wait for a warm load (David-PC UAT: 9 s from page cache). A cold
# 14 GB load still takes longer than this budget; the HTTP handler returns
# unhealthy and the client keeps polling GET /health. Do not raise this to
# minutes — that would block the start request.
OWNED_HEALTH_ATTEMPTS = 60
OWNED_HEALTH_DELAY_SECONDS = 0.5
OWNED_HEALTH_BUDGET_SECONDS = OWNED_HEALTH_ATTEMPTS * OWNED_HEALTH_DELAY_SECONDS

PROCESS_IDENTITY_MISMATCH = "process_identity_mismatch"
PROCESS_IDENTITY_UNPROVEN = "process_identity_unproven"


def argv_for_host(argv: list[str]) -> list[str]:
    """On Windows, prefix ``sys.executable`` for shebang/python test fixtures.

    Hosted Windows cannot exec a ``#!`` script. Real ``llama-server.exe`` is
    unchanged. Linux/macOS keep the existing direct-exec path.
    """
    if not argv or os.name != "nt":
        return list(argv)
    path = Path(argv[0])
    if not _python_fixture(path):
        return list(argv)
    return [sys.executable, *argv]


def _python_fixture(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() == ".py":
        return True
    try:
        with path.open("rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    return head.startswith(b"#!") and b"python" in head.lower()


def normalize_executable(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(os.path.normpath(path))


def identities_match(expected: ProcessIdentity, observed: ProcessIdentity) -> bool:
    if expected.pid != observed.pid:
        return False
    if abs(expected.create_time - observed.create_time) > CREATE_TIME_TOLERANCE_SECONDS:
        return False
    return normalize_executable(expected.executable) == normalize_executable(observed.executable)


def classify_identity(
    identity: ProcessIdentity,
    *,
    inspector: ProcessInspector | None = None,
) -> IdentityVerdict:
    current = (inspector or PsutilInspector()).identity_of(identity.pid)
    if current is None:
        return "gone"
    if identities_match(identity, current):
        return "match"
    return "mismatch"


class ProcessInspector:
    """Read-only process identity. Tests inject fixtures; never kill here."""

    def identity_of(self, pid: int) -> ProcessIdentity | None:
        raise NotImplementedError

    def listen_ports(self, pid: int) -> list[int] | None:
        """Listening TCP ports for pid and children.

        Returns ``None`` when connections cannot be inspected (do not guess).
        """
        raise NotImplementedError


class PsutilInspector(ProcessInspector):
    def identity_of(self, pid: int) -> ProcessIdentity | None:
        try:
            process = psutil.Process(pid)
            if not process.is_running():
                return None
            try:
                executable = process.exe() or ""
            except (psutil.AccessDenied, psutil.ZombieProcess):
                executable = ""
            return ProcessIdentity(
                pid=int(pid),
                create_time=float(process.create_time()),
                executable=normalize_executable(executable),
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None

    def listen_ports(self, pid: int) -> list[int] | None:
        try:
            process = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return []
        except psutil.AccessDenied:
            return None
        targets = [process]
        try:
            targets.extend(process.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        ports: set[int] = set()
        denied = False
        for item in targets:
            try:
                for conn in item.net_connections(kind="inet"):
                    if conn.status == psutil.CONN_LISTEN and conn.laddr:
                        ports.add(int(conn.laddr.port))
            except psutil.AccessDenied:
                denied = True
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        if denied and not ports:
            return None
        return sorted(ports)


class ProcessSupervisor:
    def __init__(self, *, inspector: ProcessInspector | None = None) -> None:
        self.inspector = inspector or PsutilInspector()
        self._children: dict[int, subprocess.Popen[bytes]] = {}
        self._log_pumps: dict[int, threading.Thread] = {}
        self._log_writers: dict[int, RotatingLogWriter] = {}

    def start(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
        log_path: Path | None = None,
    ) -> ProcessIdentity:
        stdout: IO[bytes] | int = subprocess.DEVNULL
        stderr: IO[bytes] | int = subprocess.DEVNULL
        writer: RotatingLogWriter | None = None
        if log_path is not None:
            writer = RotatingLogWriter(log_path)
            banner = (
                f"# workbench llama-server start {utc_now()}\n"
                f"# argv: {argv_for_host(argv)}\n"
            ).encode("utf-8")
            writer.write(banner)
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
        process = subprocess.Popen(  # noqa: S603 - argv is built from managed records
            argv_for_host(argv),
            cwd=str(cwd) if cwd else None,
            stdout=stdout,
            stderr=stderr,
        )
        pid = int(process.pid)
        self._children[pid] = process
        if writer is not None and process.stdout is not None:
            self._log_writers[pid] = writer
            pump = threading.Thread(
                target=pump_stream_to_log,
                args=(process.stdout, writer),
                name=f"llama-server-log-{pid}",
                daemon=True,
            )
            self._log_pumps[pid] = pump
            pump.start()
        elif writer is not None:
            writer.close()
        identity = self.inspector.identity_of(pid)
        if identity is None:
            return ProcessIdentity(pid=pid, create_time=0.0, executable="")
        return identity

    def _release_log(self, pid: int) -> None:
        pump = self._log_pumps.pop(int(pid), None)
        if pump is not None and pump.is_alive():
            pump.join(timeout=1.0)
        writer = self._log_writers.pop(int(pid), None)
        if writer is not None:
            writer.close()

    def classify(self, identity: ProcessIdentity) -> IdentityVerdict:
        return classify_identity(identity, inspector=self.inspector)

    def launched_still_running(self, pid: int) -> bool:
        """True only for a child this supervisor launched that has not exited."""
        child = self._children.get(int(pid))
        if child is None:
            return False
        return child.poll() is None

    def owns_listen(self, identity: ProcessIdentity, port: int) -> bool | None:
        if self.classify(identity) != "match":
            return False
        ports = self.inspector.listen_ports(identity.pid)
        if ports is None:
            return None
        return int(port) in ports

    def stop(self, identity: ProcessIdentity, *, timeout: float = 5.0) -> None:
        """Terminate only the process that still matches ``identity``.

        Callers that replace ``runtimes/local-pin`` (``stop_first`` pin) must
        not copy until this returns. On Windows a still-living child or an
        open cwd/exe handle makes ``shutil.rmtree`` fail with WinError 32.
        """
        verdict = self.classify(identity)
        if verdict == "mismatch":
            raise ManagerError(
                "Refusing to terminate a process that does not match the owned "
                "pid, executable, or creation identity.",
                code=PROCESS_IDENTITY_MISMATCH,
                status_code=409,
            )
        if verdict == "gone":
            child = self._children.pop(identity.pid, None)
            if child is not None:
                try:
                    child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
            self._release_log(identity.pid)
            return
        child = self._children.pop(identity.pid, None)
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                child.kill()
                try:
                    child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
        self._stop_process_tree(identity.pid, timeout=timeout)
        self.wait_until_gone(identity.pid, timeout=timeout)
        if self.classify(identity) == "match":
            self._stop_process_tree(identity.pid, timeout=timeout, force=True)
            self.wait_until_gone(identity.pid, timeout=timeout)
        self._release_log(identity.pid)

    def wait_until_gone(self, pid: int, *, timeout: float = 5.0) -> None:
        """Poll until the PID is gone. Does not terminate; callers must have verified identity."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_running(pid):
                return
            time.sleep(0.05)

    def is_running(self, pid: int | None) -> bool:
        if pid is None:
            return False
        return self.inspector.identity_of(int(pid)) is not None

    def _stop_process_tree(self, pid: int, *, timeout: float, force: bool = False) -> None:
        try:
            process = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        descendants: list[psutil.Process] = []
        try:
            descendants = process.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            descendants = []
        targets = [*descendants, process]
        for item in targets:
            try:
                if force:
                    item.kill()
                else:
                    item.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        _gone, alive = psutil.wait_procs(targets, timeout=timeout)
        if not alive:
            return
        for item in alive:
            try:
                item.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        psutil.wait_procs(alive, timeout=timeout)

    def resource_usage(self, identity: ProcessIdentity | None) -> ResourceUsage:
        if identity is None or self.classify(identity) != "match":
            return ResourceUsage(available=False, reason="owned process is not running")
        process = psutil.Process(identity.pid)
        memory = process.memory_info()
        return ResourceUsage(
            available=True,
            cpu_percent=float(process.cpu_percent(interval=0.05)),
            rss_bytes=int(memory.rss),
        )


class HttpProbe:
    def __init__(self, *, timeout: float = 2.0) -> None:
        self.timeout = timeout

    def health(self, endpoint: str) -> HealthReport:
        candidates = _health_urls(endpoint)
        last_error = "no health URL attempted"
        for url in candidates:
            try:
                response = httpx.get(url, timeout=self.timeout)
                if response.status_code < 400:
                    return HealthReport(
                        healthy=True,
                        endpoint=endpoint,
                        checked=utc_now(),
                        detail=f"{url} -> {response.status_code}",
                    )
                last_error = f"{url} -> {response.status_code}"
                if response.status_code == 404:
                    continue
            except httpx.HTTPError as exc:
                last_error = str(exc)
        return HealthReport(
            healthy=False,
            endpoint=endpoint,
            checked=utc_now(),
            detail=last_error,
        )

    def props(self, endpoint: str) -> ServerProperties | None:
        """Read llama-server ``GET /props``; ``None`` when the endpoint does not offer it.

        Only a healthy deployment is asked. A non-llama OpenAI-compatible
        endpoint may legitimately return 404 or a different shape; that is
        recorded as "nothing reported", never as a failure of the deployment.
        """
        url = _props_url(endpoint)
        try:
            response = httpx.get(url, timeout=self.timeout)
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        return server_properties_from_payload(payload, source_url=url)

    def smoke(self, endpoint: str) -> tuple[bool, str]:
        url = _chat_url(endpoint)
        payload = {
            "model": "workbench-smoke",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
        }
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
            if response.status_code < 400:
                return True, f"{url} -> {response.status_code}"
            return False, f"{url} -> {response.status_code} {response.text[:200]}"
        except httpx.HTTPError as exc:
            return False, str(exc)


def wait_for_health(probe: HttpProbe, endpoint: str, *, attempts: int = 20, delay: float = 0.1) -> HealthReport:
    report = probe.health(endpoint)
    for _ in range(attempts):
        if report.healthy:
            return report
        time.sleep(delay)
        report = probe.health(endpoint)
    return report


def wait_for_owned_health(
    probe: HttpProbe,
    endpoint: str,
    supervisor: ProcessSupervisor,
    identity: ProcessIdentity,
    *,
    port: int | None = None,
    attempts: int = OWNED_HEALTH_ATTEMPTS,
    delay: float = OWNED_HEALTH_DELAY_SECONDS,
) -> tuple[IdentityVerdict, HealthReport, bool | None]:
    """Probe health only while the launched process still matches identity.

    Returns ``(verdict, report, owns_listen)``. ``owns_listen`` is ``None``
    when sockets cannot be inspected or no port was supplied.

    A healthy endpoint with ``owns_listen is None`` is not ownership. Keep
    waiting until listen is proven, denied, the process exits, or timeout.
    """
    report = probe.health(endpoint)
    owns: bool | None = None
    for _ in range(attempts):
        verdict = supervisor.classify(identity)
        if verdict != "match":
            return verdict, report, False
        if not supervisor.launched_still_running(identity.pid):
            return "gone", report, False
        if port is not None:
            owns = supervisor.owns_listen(identity, port)
        if report.healthy:
            if owns is True:
                return "match", report, True
            if owns is False:
                return "match", report, False
        time.sleep(delay)
        report = probe.health(endpoint)
    verdict = supervisor.classify(identity)
    if verdict != "match" or not supervisor.launched_still_running(identity.pid):
        return "gone" if verdict == "match" else verdict, report, False
    if port is not None:
        owns = supervisor.owns_listen(identity, port)
    return verdict, report, owns


def _health_urls(endpoint: str) -> list[str]:
    base = endpoint.rstrip("/")
    urls = [f"{base}/health"]
    if base.endswith("/v1"):
        urls.append(f"{base[:-3]}/health")
        urls.append(f"{base}/models")
    else:
        urls.append(f"{base}/v1/models")
    return urls


def _chat_url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _props_url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/props"


def server_properties_from_payload(payload: dict[str, Any], *, source_url: str) -> ServerProperties:
    """Copy the b11045 ``/props`` fields the workbench records. Unknown keys are ignored."""
    generation = payload.get("default_generation_settings")
    n_ctx = generation.get("n_ctx") if isinstance(generation, dict) else None
    return ServerProperties(
        fetched=utc_now(),
        source_url=source_url,
        build_info=_optional_str(payload.get("build_info")),
        model_alias=_optional_str(payload.get("model_alias")),
        model_path=_optional_str(payload.get("model_path")),
        n_ctx=int(n_ctx) if isinstance(n_ctx, int) else None,
        total_slots=(
            int(payload["total_slots"]) if isinstance(payload.get("total_slots"), int) else None
        ),
        modalities=_bool_map(payload.get("modalities")),
        chat_template_caps=_bool_map(payload.get("chat_template_caps")),
        chat_template=_optional_str(payload.get("chat_template")),
        bos_token=_optional_str(payload.get("bos_token")),
        eos_token=_optional_str(payload.get("eos_token")),
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _bool_map(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {str(key): bool(item) for key, item in value.items() if isinstance(item, bool)}
