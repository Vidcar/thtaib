"""Windows process-tree lifecycle shared by previews and native host tools."""

from __future__ import annotations

import ctypes
import locale
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

import psutil

from workbench_backend.errors import HarnessError


def stop_process_tree(process: subprocess.Popen, job: "WindowsJob | None" = None, *, retain_job_on_failure: bool = False) -> bool:
    """Confirm an owned process tree has settled without targeting a historical PID."""
    if job is not None:
        stopped = job.stop(retain_on_failure=True) if retain_job_on_failure else job.stop()
        if process.poll() is None and not stopped:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            return False
        return stopped
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        for child in reversed(descendants):
            child.terminate()
        parent.terminate()
        _, alive = psutil.wait_procs([*descendants, parent], timeout=3)
        for child in alive:
            child.kill()
        _, alive = psutil.wait_procs(alive, timeout=3)
        if not alive:
            process.wait(timeout=3)
        return not alive
    except psutil.NoSuchProcess:
        process.poll()
        return True
    except (psutil.AccessDenied, OSError):
        return False


class WindowsJob:
    """Own a Windows process tree even if its launcher exits first."""

    def __init__(self, handle: int):
        self.handle = handle

    @classmethod
    def attach_suspended(cls, process: subprocess.Popen) -> "WindowsJob":
        return cls._attach(process, suspended=True)

    @classmethod
    def attach_running(cls, pid: int) -> "WindowsJob":
        """Attach a childless worker before its browser-launch command is allowed.

        Callers must enforce that launch barrier. This complements suspended
        native-command startup without introducing a second process owner.
        """
        return cls._attach(psutil.Process(pid), suspended=False)

    @classmethod
    def _attach(cls, process: subprocess.Popen | psutil.Process, *, suspended: bool) -> "WindowsJob":
        from ctypes import wintypes

        class _BasicLimits(ctypes.Structure):
            _fields_ = [
                ("per_process_user_time", ctypes.c_int64),
                ("per_job_user_time", ctypes.c_int64),
                ("limit_flags", wintypes.DWORD),
                ("minimum_working_set", ctypes.c_size_t),
                ("maximum_working_set", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority_class", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "read_operations", "write_operations", "other_operations",
                "read_bytes", "write_bytes", "other_bytes",
            )]

        class _ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", _BasicLimits), ("io", _IoCounters),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create owned process job")
        job = cls(handle)
        process_handle = None
        thread_handle = None
        try:
            limits = _ExtendedLimits()
            limits.basic.limit_flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError(ctypes.get_last_error(), "Could not configure owned process job")
            process_handle = kernel.OpenProcess(0x0101, False, process.pid)  # SET_QUOTA | TERMINATE
            if not process_handle or not kernel.AssignProcessToJobObject(handle, process_handle):
                raise OSError(ctypes.get_last_error(), "Could not attach process to its job")
            # CREATE_SUSPENDED prevents the command from spawning a child before
            # the job owns it. A suspended new process has one initial thread.
            if suspended:
                thread_ids = [thread.id for thread in psutil.Process(process.pid).threads()]
                if len(thread_ids) != 1:
                    raise OSError("Owned process did not have one suspended startup thread")
                thread_handle = kernel.OpenThread(0x0002, False, thread_ids[0])  # THREAD_SUSPEND_RESUME
                if not thread_handle or kernel.ResumeThread(thread_handle) == 0xFFFFFFFF:
                    raise OSError(ctypes.get_last_error(), "Could not resume owned process")
            return job
        except BaseException:
            job.stop()
            running = process.poll() is None if isinstance(process, subprocess.Popen) else process.is_running()
            if running:
                process.terminate()
                process.wait(timeout=3)
            raise
        finally:
            if thread_handle:
                kernel.CloseHandle(thread_handle)
            if process_handle:
                kernel.CloseHandle(process_handle)

    def stop(self, *, retain_on_failure: bool = False) -> bool:
        if not self.handle:
            return True
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        class _Accounting(ctypes.Structure):
            _fields_ = [
                ("total_user_time", ctypes.c_int64), ("total_kernel_time", ctypes.c_int64),
                ("period_user_time", ctypes.c_int64), ("period_kernel_time", ctypes.c_int64),
                ("page_faults", wintypes.DWORD), ("total_processes", wintypes.DWORD),
                ("active_processes", wintypes.DWORD), ("terminated_processes", wintypes.DWORD),
            ]
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        # Retain synchronization handles for the job members before requesting
        # termination. Job accounting can reach zero before a child process's
        # exit has signalled and completed inherited-handle cleanup.
        process_handles = []
        for capacity in (64, 256, 1024, 4096):
            class _ProcessIds(ctypes.Structure):
                _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                            ("ids", ctypes.c_size_t * capacity)]
            members = _ProcessIds()
            if kernel.QueryInformationJobObject(self.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None):
                for pid in members.ids[:members.count]:
                    handle = kernel.OpenProcess(0x00100000, False, pid)
                    if handle:
                        process_handles.append(handle)
                break
            if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                break
        kernel.TerminateJobObject(self.handle, 1)
        # A venv Python/package launcher may exit before its child releases the
        # inherited log handle. Waiting for only Popen.pid is insufficient on
        # Windows: retain the job until every owned process has actually exited.
        empty = False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            accounting = _Accounting()
            if not kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                break
            if accounting.active_processes == 0:
                empty = True
                break
            threading.Event().wait(.01)
        for handle in process_handles:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if kernel.WaitForSingleObject(handle, remaining_ms) != 0:
                empty = False
            kernel.CloseHandle(handle)
        # Retryable owners keep the exact job identity until stop is confirmed.
        # Final owners close it here, retaining kill-on-close cleanup semantics.
        if not empty and retain_on_failure:
            return False
        closed = bool(kernel.CloseHandle(self.handle))
        if closed or not retain_on_failure:
            self.handle = 0
        return empty and closed


def run_windows_command(command: str, *, cwd: Path, env: dict[str, str], timeout: float,
                        cancel_requested: Callable[[], bool] | None = None) -> subprocess.CompletedProcess[str]:
    """Own the native cmd.exe tree until it exits, times out or is cancelled.

    This changes only host process lifetime. Deep Agents still owns the tool,
    approvals, execution protocol and model loop.
    """
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004
    # File capture avoids pipe-reader threads held open by grandchildren after
    # cmd.exe exits. The job, rather than pipe EOF, establishes quiescence.
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(command, shell=True, cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file, creationflags=flags)
        job = None
        try:
            job = WindowsJob.attach_suspended(process)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if cancel_requested is not None and cancel_requested():
                    code = 130
                    break
                if remaining <= 0:
                    code = 124
                    break
                try:
                    code = process.wait(timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            stopped = job.stop()
            job = None
            if not stopped:
                raise HarnessError("The command's process tree could not be confirmed stopped. Inspect its effects before continuing.",
                    code="shell_stop_unconfirmed", status_code=409)
            stdout_file.seek(0)
            stderr_file.seek(0)
            # Host commands retain their Windows locale even when the backend
            # enables UTF-8 for native JSON/text protocols.
            encoding = locale.getencoding()
            stdout = stdout_file.read().decode(encoding, errors="replace")
            stderr = stderr_file.read().decode(encoding, errors="replace")
            if code == 124:
                stderr += f"\nCommand timed out after {timeout:g} seconds; its owned process tree has stopped."
            elif code == 130:
                stderr += "\nCommand cancelled; its owned process tree has stopped."
            return subprocess.CompletedProcess(command, code, stdout, stderr)
        finally:
            stopped = job.stop() if job is not None else True
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            if not stopped:
                raise HarnessError("The command's process tree could not be confirmed stopped. Inspect its effects before continuing.",
                    code="shell_stop_unconfirmed", status_code=409)
