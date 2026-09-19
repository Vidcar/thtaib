"""Managed-process helpers. Connected endpoints never use this supervisor."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import HealthReport, ResourceUsage


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


class ProcessSupervisor:
    def __init__(self) -> None:
        self._children: dict[int, subprocess.Popen[bytes]] = {}

    def start(self, argv: list[str], *, cwd: Path | None = None) -> int:
        process = subprocess.Popen(  # noqa: S603 - argv is built from managed records
            argv_for_host(argv),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._children[int(process.pid)] = process
        return int(process.pid)

    def stop(self, pid: int, *, timeout: float = 5.0) -> None:
        """Terminate the managed process tree and wait until it is gone.

        Callers that replace ``runtimes/local-pin`` (``stop_first`` pin) must
        not copy until this returns. On Windows a still-living child or an
        open cwd/exe handle makes ``shutil.rmtree`` fail with WinError 32.
        """
        child = self._children.pop(pid, None)
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
        self._stop_process_tree(pid, timeout=timeout)
        self.wait_until_gone(pid, timeout=timeout)

    def wait_until_gone(self, pid: int, *, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_running(pid):
                return
            time.sleep(0.05)
        if self.is_running(pid):
            self._stop_process_tree(pid, timeout=timeout, force=True)
        while time.monotonic() < deadline + timeout:
            if not self.is_running(pid):
                return
            time.sleep(0.05)

    def is_running(self, pid: int | None) -> bool:
        if pid is None:
            return False
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

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

    def resource_usage(self, pid: int | None) -> ResourceUsage:
        if not self.is_running(pid):
            return ResourceUsage(available=False, reason="process is not running")
        process = psutil.Process(pid)
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
