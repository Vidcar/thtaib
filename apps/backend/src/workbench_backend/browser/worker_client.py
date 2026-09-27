"""Backend-only management of the same Chrome worker used by MCPAdapter.

The official stdio transport owns MCP messages. This client carries only typed
management requests and temporary live frames, never unrestricted CDP access.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import psutil
from fastmcp.client.transports import StdioTransport

from workbench_backend.errors import HarnessError
from workbench_backend.process_tree import WindowsJob


class _OwnedStdioTransport(StdioTransport):
    """Keep the official transport while attaching ownership before initialize."""

    def __init__(self, owner, **kwargs):
        self.owner = owner
        super().__init__(**kwargs)

    @asynccontextmanager
    async def connect_session(self, **kwargs):
        async with super().connect_session(**kwargs) as session:
            await self.owner.connect()
            yield session


class BrowserWorkerClient:
    def __init__(
        self, node: Path, worker_script: Path, profile_dir: Path, output_dir: Path,
        *, chrome_path: Path | None = None,
    ):
        self.profile_dir = profile_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = output_dir / f".worker-{uuid.uuid4().hex}.json"
        self._token = secrets.token_urlsafe(48)
        self._http: httpx.AsyncClient | None = None
        self._job: WindowsJob | None = None
        self.pid: int | None = None
        self._closed = False
        env = {
            "WORKBENCH_BROWSER_TOKEN": self._token,
            "WORKBENCH_BROWSER_MANIFEST": str(self._manifest),
            "WORKBENCH_BROWSER_PROFILE": str(profile_dir),
            "WORKBENCH_BROWSER_OUTPUT": str(output_dir),
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        }
        if chrome_path is not None:
            env["WORKBENCH_CHROME_PATH"] = str(chrome_path)
        self.transport = _OwnedStdioTransport(self,
            command=str(node), args=[str(worker_script)], env=env,
            cwd=str(worker_script.parent), keep_alive=False,
            log_file=output_dir / ".worker.log",
        )

    async def connect(self) -> None:
        """After MCP client entry, own the childless Node tree before Chrome starts."""
        if self._closed:
            raise HarnessError("The browser worker has closed.", code="browser_session_closed", status_code=409)
        if self._http is not None:
            return
        deadline = asyncio.get_running_loop().time() + 15
        manifest: dict[str, Any] | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                manifest = json.loads(await asyncio.to_thread(self._manifest.read_text, encoding="utf-8"))
                break
            except (OSError, ValueError):
                await asyncio.sleep(.025)
        if not manifest or not isinstance(manifest.get("pid"), int) or not isinstance(manifest.get("port"), int):
            raise HarnessError("The browser worker did not become ready.", code="browser_worker_failed", status_code=409)
        port = manifest["port"]
        if not 0 < port < 65536:
            raise HarnessError("The browser worker returned an invalid private address.", code="browser_worker_failed", status_code=409)
        self.pid = manifest["pid"]
        process = psutil.Process(self.pid)
        # No public browser call is allowed before this handshake. Attaching
        # while childless closes the startup race left by ordinary stdio spawn.
        unexpected = [child for child in process.children() if child.name().lower() != "conhost.exe"]
        if unexpected:
            children = ", ".join(child.name() for child in unexpected)
            raise HarnessError(f"The browser worker started a child before its process owner was ready ({children}).", code="browser_process_unowned", status_code=409)
        if sys.platform == "win32":
            self._job = WindowsJob.attach_running(self.pid)
        self._http = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx.Timeout(40, connect=3), trust_env=False,
        )
        await self.get_state()
        await self._request("POST", "/authorize", json={})

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        if self._http is None or self._closed:
            raise HarnessError("The browser worker is unavailable.", code="browser_session_lost", status_code=409)
        try:
            response = await self._http.request(method, endpoint, **kwargs)
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HarnessError("The browser worker was lost. Inspect the page before resetting; actions were not repeated.", code="browser_session_lost", status_code=409) from exc
        if response.is_error:
            raise HarnessError(
                result.get("error", "The browser action failed."),
                code=result.get("code", "browser_worker_failed"), status_code=response.status_code,
            )
        return result

    async def start(self) -> dict[str, Any]:
        await self.connect()
        return await self._request("POST", "/start", json={})

    async def get_state(self) -> dict[str, Any]:
        return await self._request("GET", "/state")

    async def action(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/actions", json=payload)

    async def validate_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/validate", json=payload)

    async def reset_input(self) -> dict[str, Any]:
        return await self._request("POST", "/reset-input", json={})

    async def set_active(self, index: int) -> dict[str, Any]:
        return await self._request("POST", "/active", json={"index": index})

    async def set_streaming(self, visible: bool) -> dict[str, Any]:
        return await self._request("POST", "/stream", json={"visible": visible})

    async def poll(self, last_frame_seq: int = 0) -> dict[str, Any]:
        return await self._request("GET", "/poll", params={"after": last_frame_seq})

    async def drain_downloads(self) -> list[dict[str, Any]]:
        return (await self.poll()).get("downloads", [])

    async def ack_download(self, download_id: str) -> None:
        await self._request("POST", "/ack-download", json={"download_id": download_id})

    async def acknowledge_modal(self, kind: str) -> dict[str, Any]:
        """Clear only an upstream-completed modal observation, never repeat it."""
        return await self._request("POST", "/ack-modal", json={"kind": kind})

    async def set_attribution(self, attribution: dict[str, Any] | None) -> None:
        await self._request("POST", "/attribution", json={"attribution": attribution})

    async def close(self) -> None:
        """Flush the profile, disconnect MCP and confirm the entire owned tree stopped."""
        if self._closed:
            return
        try:
            if self._http is not None:
                try:
                    await self._request("POST", "/close", json={})
                except HarnessError:
                    pass  # Lost workers still require tree-wide termination.
        finally:
            self._closed = True
            if self._http is not None:
                await self._http.aclose()
            try:
                await self.transport.close()
            finally:
                stopped = await asyncio.to_thread(self._job.stop) if self._job is not None else True
                self._job = None
                await asyncio.to_thread(self._manifest.unlink, missing_ok=True)
                if not stopped:
                    raise HarnessError("Chrome's complete process tree could not be confirmed stopped.", code="browser_stop_unconfirmed", status_code=409)
