"""Contended project-mutation admission must not stall the worker pool.

The child process is the watchdog boundary. A stuck lease fails this test
when the parent times out, instead of hanging the verification runner.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import traceback
import unittest
from pathlib import Path


class MutationAdmissionWatchdogTests(unittest.TestCase):
    def test_compiled_middleware_survives_executor_contention(self):
        backend = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["WORKBENCH_DATA_ROOT"] = tempfile.mkdtemp(prefix="mutation-admission-parent-")
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "tests.test_mutation_admission", "--child"],
                cwd=backend,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired as error:
            self.fail("mutation admission hung past the watchdog:\n" + _output(error))
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
        self.assertIn("MUTATION_ADMISSION_OK", completed.stdout)


def _output(error: subprocess.TimeoutExpired) -> str:
    stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
    stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
    return stdout + "\n" + stderr


def run_child() -> None:
    root = tempfile.mkdtemp(prefix="mutation-admission-child-")
    os.environ["WORKBENCH_DATA_ROOT"] = root
    try:
        asyncio.run(_exercise())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print("MUTATION_ADMISSION_OK")


async def _exercise() -> None:
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mutation-admission")
    loop.set_default_executor(executor)
    try:
        await _low_contention_control()
        await _sync_apply_edits_borrows()
        await _contended_native_and_apply()
        await _cancel_queued_and_settling()
        await _failure_approval_and_revocation()
        await _read_and_other_project_continue()
        await _lease_is_reusable_after_contention()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def _run(project: Path, tools: list[str], call_id: str = "call"):
    from workbench_backend.agents.schemas import AgentRun, AgentRunStatus

    return AgentRun(
        id="mutation-" + project.name,
        deployment_id="fixture",
        task="mutate",
        project_path=str(project),
        status=AgentRunStatus.running,
        enabled_tools=tools,
        presented_tools=tools,
        created_at="2026-10-01T00:00:00Z",
        updated_at="2026-10-01T00:00:00Z",
    )


def _request(name: str, args: dict, call_id: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        tool_call={"name": name, "args": args, "id": call_id},
        runtime=SimpleNamespace(state={"messages": []}),
    )


def _message(name: str, call_id: str, content: str):
    from langchain_core.messages import ToolMessage

    return ToolMessage(content=content, name=name, tool_call_id=call_id)


async def _write(middleware, project: Path, name: str, call_id: str, content: str = "written"):
    request = _request("write_file", {"file_path": name, "content": content}, call_id)

    async def handler(_request):
        def work():
            target = project / name.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return _message("write_file", call_id, content)
        return await asyncio.to_thread(work)

    return await middleware.awrap_tool_call(request, handler)


async def _low_contention_control() -> None:
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware

    with tempfile.TemporaryDirectory() as area:
        project = Path(area)
        middleware = WorkbenchHarnessMiddleware(_run(project, ["write_file"]))
        await asyncio.wait_for(_write(middleware, project, "one.txt", "control"), timeout=5)
        if (project / "one.txt").read_text(encoding="utf-8") != "written":
            raise AssertionError("low-contention control did not write")


async def _sync_apply_edits_borrows() -> None:
    """The sync hook must mark the lease admitted before apply_edits acquires it."""
    from workbench_backend.agents.file_operations import apply_edits_tool
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware

    with tempfile.TemporaryDirectory() as area:
        project = Path(area)
        original = "alpha VALUE omega\n"
        (project / "sync.txt").write_bytes(original.encode("utf-8"))
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        run = _run(project, ["apply_edits"])
        middleware = WorkbenchHarnessMiddleware(run)
        editor = apply_edits_tool(run)
        request = _request("apply_edits", {
            "file_path": "sync.txt",
            "edits": [{"old_string": "VALUE", "new_string": "SYNCED"}],
            "base_sha256": digest,
        }, "sync-apply")

        def handler(_request):
            content = editor.invoke(request.tool_call["args"])
            return _message("apply_edits", "sync-apply", content if isinstance(content, str) else str(content))

        done = threading.Event()
        box: dict = {}

        def worker():
            try:
                box["result"] = middleware.wrap_tool_call(request, handler)
            except Exception as exc:
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=worker, daemon=True).start()
        if not done.wait(5):
            raise AssertionError("sync apply_edits did not return; the nested lease acquire is stuck")
        if "error" in box:
            raise box["error"]
        if "SYNCED" not in (project / "sync.txt").read_text(encoding="utf-8"):
            raise AssertionError("sync apply_edits did not write")


async def _contended_native_and_apply() -> None:
    from workbench_backend.agents.file_operations import apply_edits_tool
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware

    with tempfile.TemporaryDirectory() as area:
        project = Path(area)
        tools = ["write_file", "apply_edits"]
        run = _run(project, tools)
        middleware = WorkbenchHarnessMiddleware(run)
        original = "alpha VALUE omega\n"
        for index in range(4):
            path = project / f"edit-{index}.txt"
            path.write_bytes(original.encode("utf-8"))
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        editor = apply_edits_tool(run)

        async def apply(index: int):
            call_id = f"apply-{index}"
            request = _request("apply_edits", {
                "file_path": f"edit-{index}.txt",
                "edits": [{"old_string": "VALUE", "new_string": f"CHANGED-{index}"}],
                "base_sha256": digest,
            }, call_id)

            async def handler(_request):
                content = await editor.ainvoke(request.tool_call["args"])
                return _message("apply_edits", call_id, content if isinstance(content, str) else str(content))

            return await middleware.awrap_tool_call(request, handler)

        writes = [_write(middleware, project, f"native-{index}.txt", f"native-{index}", f"native-{index}") for index in range(4)]
        results = await asyncio.wait_for(asyncio.gather(*writes, *(apply(index) for index in range(4))), timeout=15)
        if len(results) != 8:
            raise AssertionError(f"expected 8 mutations, got {len(results)}")
        for index in range(4):
            if (project / f"native-{index}.txt").read_text(encoding="utf-8") != f"native-{index}":
                raise AssertionError(f"native file {index} missing")
            edited = (project / f"edit-{index}.txt").read_text(encoding="utf-8")
            if f"CHANGED-{index}" not in edited:
                raise AssertionError(f"structured edit {index} did not apply: file={edited!r} result={getattr(results[4 + index], 'content', results[4 + index])!r}")


async def _cancel_queued_and_settling() -> None:
    from workbench_backend.agents.file_operations import file_order_lock, file_order_path
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware

    with tempfile.TemporaryDirectory() as area:
        project = Path(area)
        middleware = WorkbenchHarnessMiddleware(_run(project, ["write_file"]))
        lease = file_order_lock(file_order_path(project, "holder.txt"))
        started, release = threading.Event(), threading.Event()

        async def holder():
            request = _request("write_file", {"file_path": "holder.txt", "content": "held"}, "holder")

            async def handler(_request):
                def work():
                    started.set()
                    if not release.wait(10):
                        raise TimeoutError("holder was not released")
                    (project / "holder.txt").write_text("held", encoding="utf-8")
                    return _message("write_file", "holder", "held")
                return await asyncio.to_thread(work)

            return await middleware.awrap_tool_call(request, handler)

        holding = asyncio.create_task(holder())
        if not await asyncio.to_thread(started.wait, 5):
            raise AssertionError("admitted holder did not start")
        other = asyncio.create_task(_write(middleware, project, "other.txt", "other", "other"))
        await asyncio.wait_for(other, timeout=5)
        if (project / "other.txt").read_text(encoding="utf-8") != "other":
            raise AssertionError("a different file waited behind the held file")
        queued = [asyncio.create_task(_write(middleware, project, "holder.txt", f"queued-{index}", f"queued-{index}")) for index in range(6)]
        for _ in range(50):
            if lease.waiting() >= 6:
                break
            await asyncio.sleep(0.02)
        if lease.waiting() < 6:
            raise AssertionError(f"expected same-file waiters, saw {lease.waiting()}")
        for task in queued:
            task.cancel()
        queued_done = await asyncio.wait_for(asyncio.gather(*queued, return_exceptions=True), timeout=3)
        if not all(isinstance(item, asyncio.CancelledError) for item in queued_done):
            raise AssertionError(f"queued cancellation did not finish cleanly: {queued_done!r}")
        if (project / "holder.txt").exists():
            raise AssertionError("cancelled same-file waiter wrote before the holder")
        if lease.acquire():
            lease.release()
            raise AssertionError("queued cancellation released the admitted holder")
        release.set()
        await asyncio.wait_for(holding, timeout=5)
        if (project / "holder.txt").read_text(encoding="utf-8") != "held":
            raise AssertionError("settling holder did not finish its write")
        if not lease.acquire():
            raise AssertionError("lease stayed held after the admitted worker settled")
        lease.release()

        # Cancellation while the admitted worker is still inside its effect.
        # A fresh run avoids the unconfirmed-effect guard left by the queued cancels.
        middleware = WorkbenchHarnessMiddleware(_run(project, ["write_file"]))
        lease = file_order_lock(file_order_path(project, "settling.txt"))
        entered, finish = threading.Event(), threading.Event()

        async def settling():
            request = _request("write_file", {"file_path": "settling.txt", "content": "settled"}, "settling")

            async def handler(_request):
                def work():
                    entered.set()
                    if not finish.wait(10):
                        raise TimeoutError("settling worker was not released")
                    (project / "settling.txt").write_text("settled", encoding="utf-8")
                    return _message("write_file", "settling", "settled")
                return await asyncio.to_thread(work)

            return await middleware.awrap_tool_call(request, handler)

        task = asyncio.create_task(settling())
        if not await asyncio.to_thread(entered.wait, 5):
            raise AssertionError("settling mutation did not enter")
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        if task.done():
            raise AssertionError("cancellation abandoned the admitted worker")
        if lease.acquire():
            lease.release()
            raise AssertionError("settling cancellation released the lease early")
        finish.set()
        try:
            await asyncio.wait_for(task, timeout=5)
            raise AssertionError("settling cancellation should surface CancelledError")
        except asyncio.CancelledError:
            pass
        if (project / "settling.txt").read_text(encoding="utf-8") != "settled":
            raise AssertionError("cancelled admitted work did not settle its effect")
        if not lease.acquire():
            raise AssertionError("lease was not reusable after settling cancellation")
        lease.release()


async def _failure_approval_and_revocation() -> None:
    from langgraph.errors import GraphInterrupt
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
    from workbench_backend.state.preferences import MatchedPermissionGrant

    with tempfile.TemporaryDirectory() as area:
        project = Path(area)
        run = _run(project, ["write_file"])
        middleware = WorkbenchHarnessMiddleware(run)

        async def boom(_request):
            raise RuntimeError("mutation failed before replacement")

        try:
            await middleware.awrap_tool_call(_request("write_file", {"file_path": "boom.txt", "content": "x"}, "boom"), boom)
            raise AssertionError("tool exception should propagate when it is not a declared tool error")
        except RuntimeError:
            pass
        if (project / "boom.txt").exists():
            raise AssertionError("failed mutation wrote a file")
        # A new run proves the project lease itself is free. The failed run
        # keeps its unconfirmed-effect guard.
        await _write(WorkbenchHarnessMiddleware(_run(project, ["write_file"])), project, "after-failure.txt", "after-failure", "after-failure")

        calls = {"count": 0}
        approval_middleware = WorkbenchHarnessMiddleware(_run(project, ["write_file"]))

        async def interrupt_then_write(request):
            calls["count"] += 1
            if calls["count"] == 1:
                raise GraphInterrupt(())
            (project / "approved.txt").write_text("approved", encoding="utf-8")
            return _message("write_file", request.tool_call["id"], "approved")

        approval = _request("write_file", {"file_path": "approved.txt", "content": "approved"}, "approval")
        try:
            await approval_middleware.awrap_tool_call(approval, interrupt_then_write)
            raise AssertionError("approval interruption did not propagate")
        except GraphInterrupt:
            pass
        if (project / "approved.txt").exists():
            raise AssertionError("interrupted approval wrote before resume")
        resumed = await approval_middleware.awrap_tool_call(approval, interrupt_then_write)
        if getattr(resumed, "content", "") != "approved":
            raise AssertionError("approval resume did not return the original call")
        if (project / "approved.txt").read_text(encoding="utf-8") != "approved":
            raise AssertionError("approval resume did not apply once")

        class Revoked:
            def matching_grant_by_id(self, *_args):
                return None

        revoked_run = _run(project, ["write_file"])
        grant = MatchedPermissionGrant(
            id="grant-1", scope="always", action="write_file", arguments={"file_path": "revoked.txt"},
            created_at="2026-10-01T00:00:00Z", source_run_id=revoked_run.id, display_name="Write revoked.txt",
        )
        revoked_run.tool_authorizations["revoked"] = "saved_permission"
        revoked_run.tool_authorization_grants["revoked"] = grant
        revoked_middleware = WorkbenchHarnessMiddleware(revoked_run, grants=Revoked())
        ran = []

        async def should_not_run(_request):
            ran.append(True)
            return _message("write_file", "revoked", "ran")

        result = await revoked_middleware.awrap_tool_call(
            _request("write_file", {"file_path": "revoked.txt", "content": "no"}, "revoked"), should_not_run)
        if ran or (project / "revoked.txt").exists():
            raise AssertionError("revoked grant still performed the mutation")
        if "revoked" not in str(getattr(result, "content", result)).lower():
            raise AssertionError(f"revoked grant did not report the block: {result!r}")
        await _write(revoked_middleware, project, "after-revocation.txt", "after-revocation", "after")


async def _read_and_other_project_continue() -> None:
    from workbench_backend.agents.file_operations import file_order_lock, file_order_path
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware

    with tempfile.TemporaryDirectory() as area:
        root = Path(area)
        first, second = root / "one", root / "two"
        first.mkdir()
        second.mkdir()
        held = WorkbenchHarnessMiddleware(_run(first, ["write_file", "read_file"]))
        other = WorkbenchHarnessMiddleware(_run(second, ["write_file"]))
        neighbor = WorkbenchHarnessMiddleware(_run(first, ["write_file"], "neighbor"))
        lease = file_order_lock(file_order_path(first, "busy.txt"))
        started, release = threading.Event(), threading.Event()

        async def holder():
            request = _request("write_file", {"file_path": "busy.txt", "content": "busy"}, "busy")

            async def handler(_request):
                def work():
                    started.set()
                    if not release.wait(10):
                        raise TimeoutError("busy holder was not released")
                    (first / "busy.txt").write_text("busy", encoding="utf-8")
                    return _message("write_file", "busy", "busy")
                return await asyncio.to_thread(work)

            return await held.awrap_tool_call(request, handler)

        blocking = asyncio.create_task(holder())
        if not await asyncio.to_thread(started.wait, 5):
            raise AssertionError("project holder did not start")

        async def read():
            request = _request("read_file", {"file_path": "busy.txt"}, "read")

            async def handler(_request):
                def work():
                    return _message("read_file", "read", (first / "busy.txt").read_text(encoding="utf-8"))
                return await asyncio.to_thread(work)

            return await held.awrap_tool_call(request, handler)

        await asyncio.wait_for(asyncio.gather(
            _write(other, second, "elsewhere.txt", "elsewhere", "elsewhere"),
            _write(neighbor, first, "neighbor.txt", "neighbor", "neighbor"),
        ), timeout=5)
        if (second / "elsewhere.txt").read_text(encoding="utf-8") != "elsewhere":
            raise AssertionError("another project did not continue")
        if (first / "neighbor.txt").read_text(encoding="utf-8") != "neighbor":
            raise AssertionError("a different file in the same folder did not continue")
        if lease.acquire():
            lease.release()
            raise AssertionError("the busy file was not still admitted")
        reading = asyncio.create_task(read())
        await asyncio.sleep(0.05)
        if reading.done():
            raise AssertionError("a read of the file being written did not wait")
        release.set()
        await asyncio.wait_for(blocking, timeout=5)
        read_result = await asyncio.wait_for(reading, timeout=5)
        if getattr(read_result, "content", "") != "busy":
            raise AssertionError("the waiting read did not see the new bytes")


async def _lease_is_reusable_after_contention() -> None:
    from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware

    with tempfile.TemporaryDirectory() as area:
        project = Path(area)
        middleware = WorkbenchHarnessMiddleware(_run(project, ["write_file"]))
        await asyncio.wait_for(asyncio.gather(*[
            _write(middleware, project, f"again-{index}.txt", f"again-{index}", "again") for index in range(6)
        ]), timeout=10)
        if any((project / f"again-{index}.txt").read_text(encoding="utf-8") != "again" for index in range(6)):
            raise AssertionError("the lease did not admit a later batch")


if __name__ == "__main__":
    if "--child" in sys.argv:
        run_child()
    else:
        unittest.main()
