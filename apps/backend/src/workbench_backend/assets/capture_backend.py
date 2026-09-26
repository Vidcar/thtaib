"""Read-only Deep Agents route for a conversation's retained screenshots."""

from __future__ import annotations

import base64
import fnmatch
import re
from collections.abc import Callable

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from fastapi import HTTPException

from workbench_backend.assets.schemas import RetainedAssetListFilters, RetainedAssetOrigin
from workbench_backend.assets.service import RetainedAssetService, capture_virtual_path
from workbench_backend.inference.image_validation import CANNOT_READ_IMAGE, validate_image_bytes

_CAPTURE_PATH = re.compile(r"^/(asset_[0-9a-f]{32})\.(png|jpg|webp)$")
_READ_ONLY = "Captures are read-only retained assets."


class CaptureBackend(BackendProtocol):
    """Expose retained bytes without copying them into project or scratch files."""

    def __init__(self, assets: RetainedAssetService, session_id: str, *, image_inputs_allowed: bool | Callable[[], bool] = False) -> None:
        self.assets = assets
        self.session_id = session_id
        self.image_inputs_allowed = image_inputs_allowed

    def _entries(self) -> list[dict[str, object]]:
        assets = self.assets.list_assets(
            RetainedAssetListFilters(session_id=self.session_id, origin=RetainedAssetOrigin.capture)
        )
        return [
            {
                "path": capture_virtual_path(asset).removeprefix("/captures"),
                "is_dir": False,
                "size": asset.size_bytes,
                "modified_at": asset.observed_at,
            }
            for asset in assets
        ]

    def ls(self, path: str) -> LsResult:
        if path != "/":
            return LsResult(error="Capture path is not a directory.")
        return LsResult(entries=self._entries())

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        if limit <= 0:
            return ReadResult(no_lines_requested=True)
        match = _CAPTURE_PATH.fullmatch(file_path)
        if match is None:
            return ReadResult(error="Capture not found.")
        allowed = self.image_inputs_allowed
        if not (bool(allowed()) if callable(allowed) else bool(allowed)):
            return ReadResult(error=CANNOT_READ_IMAGE)
        try:
            asset, content = self.assets._load_content(match.group(1), session_id=self.session_id, project_path=None)
        except HTTPException as exc:
            return ReadResult(error=str(exc.detail))
        if asset.origin is not RetainedAssetOrigin.capture or capture_virtual_path(asset) != f"/captures{file_path}":
            return ReadResult(error="Capture not found.")
        try:
            validate_image_bytes(content, asset.content_type)
        except ValueError as exc:
            return ReadResult(error=f"Cannot read retained capture: {exc}")
        return ReadResult(file_data={"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"})

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None, *, max_count: int | None = None) -> GrepResult:
        return GrepResult(matches=[])

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        if path not in {None, "/"}:
            return GlobResult(matches=[])
        wanted = pattern.lstrip("/")
        return GlobResult(matches=[entry for entry in self._entries() if fnmatch.fnmatch(entry["path"].lstrip("/"), wanted)])

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READ_ONLY)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error=_READ_ONLY)

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=_READ_ONLY)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error="permission_denied") for path, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            result = self.read(path)
            if result.file_data is None:
                responses.append(FileDownloadResponse(path=path, error="file_not_found"))
            else:
                responses.append(FileDownloadResponse(path=path, content=base64.b64decode(result.file_data["content"])))
        return responses
