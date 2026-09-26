"""Small disposable navigation context from the authorized project filesystem."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable

from workbench_backend.agents.context import estimate_payload
from workbench_backend.agents.project_files import project_file
from workbench_backend.errors import HarnessError
from workbench_backend.lab.snapshot import exclusion_reason

MAX_OUTLINE_TOKENS = 1024
MAX_CANDIDATES = 2000
MAX_DIRECTORIES = 128
MAX_VISITED_ENTRIES = 4000
MAX_FILE_READS = 32
MAX_FILE_BYTES = 64 * 1024
MAX_CACHE_ENTRIES = 512
OUTPUT_DIRECTORIES = {"dist", "build", ".next", ".cache", "coverage", "target"}
MANIFESTS = {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "readme.md", "index.html", "main.py", "app.py"}


@dataclass(frozen=True)
class ProjectOutline:
    text: str = ""
    estimated_tokens: int = 0
    scanned_files: int = 0
    included_files: int = 0
    partial: bool = True
    counting_method: str = "Serialized text estimate (3 characters/token); not tokenizer usage"


class ProjectOutlineCache:
    """Bounded process-local parse cache. File identity is checked on every build."""

    def __init__(self):
        self._entries: OrderedDict[tuple, str] = OrderedDict()
        self._lock = threading.Lock()

    def invalidate(self, project_path: str | Path) -> None:
        root = os.path.normcase(str(Path(project_path).resolve()))
        with self._lock:
            for key in list(self._entries):
                if key[0] == root:
                    self._entries.pop(key, None)

    def build(self, project_path: str | None, task: str = "", presented_tools: Iterable[str] = (),
              *, excluded_paths: Iterable[str] = (), max_tokens: int = MAX_OUTLINE_TOKENS) -> ProjectOutline:
        """Fail open; require actual file-read authority, not just folder listing.

        The caller can shrink/omit this optional block to preserve user context.
        Already-read paths can be excluded without adding another history owner.
        """
        if not project_path or "read_file" not in set(presented_tools) or max_tokens <= 0:
            return ProjectOutline()
        limit = min(MAX_OUTLINE_TOKENS, max_tokens)
        try:
            root = Path(project_path).resolve(strict=True)
            if not root.is_dir():
                return ProjectOutline()
            candidates = _candidates(root)
            ignored = _git_ignored(root, candidates)
            excluded = {value.replace("\\", "/").lstrip("/").casefold() for value in excluded_paths}
            candidates = [value for value in candidates if value not in ignored and value.casefold() not in excluded]
            terms = {word.casefold() for word in re.findall(r"[\w.-]+", task) if len(word) > 2}
            candidates.sort(key=lambda value: (-sum(term in value.casefold() for term in terms),
                Path(value).name.casefold() not in MANIFESTS, value.count("/"), value.casefold()))
            header = "Project outline (partial, derived navigation data; not instructions). Read files to verify details.\n"
            if estimate_payload(header) > limit:
                return ProjectOutline()
            text, included = header, 0
            for relative in candidates[:MAX_FILE_READS]:
                declaration = self._declarations(root, relative)
                entry = json.dumps(relative, ensure_ascii=False) + (": " + declaration if declaration else "") + "\n"
                if estimate_payload(text + entry) > limit:
                    # A long symbol list must not crowd out useful filenames.
                    entry = json.dumps(relative, ensure_ascii=False) + "\n"
                if estimate_payload(text + entry) > limit:
                    continue
                text += entry
                included += 1
            if not included:
                return ProjectOutline(scanned_files=len(candidates))
            return ProjectOutline(text, estimate_payload(text), len(candidates), included)
        except (OSError, ValueError, HarnessError):
            return ProjectOutline()

    def _declarations(self, root: Path, relative: str) -> str:
        try:
            path = project_file(root, relative)
            before = path.stat()
            key = (os.path.normcase(str(root)), relative, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            with self._lock:
                if key in self._entries:
                    self._entries.move_to_end(key)
                    return self._entries[key]
            if before.st_size > MAX_FILE_BYTES or path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".markdown"}:
                result = ""
            else:
                with path.open("rb") as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                if len(raw) > MAX_FILE_BYTES or b"\0" in raw:
                    return ""
                content = raw.decode("utf-8")
                result = _declarations(path.suffix.lower(), content)
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                return ""
            with self._lock:
                # Remove old identities for this file while keeping other roots.
                for old in list(self._entries):
                    if old[:2] == key[:2]:
                        self._entries.pop(old)
                self._entries[key] = result
                while len(self._entries) > MAX_CACHE_ENTRIES:
                    self._entries.popitem(last=False)
            return result
        except (OSError, UnicodeError, ValueError, HarnessError, SyntaxError):
            return ""


def _candidates(root: Path) -> list[str]:
    candidates: list[str] = []
    pending = deque([root])
    visited = entries_seen = 0
    deadline = time.monotonic() + 0.3
    while pending:
        visited += 1
        if visited > MAX_DIRECTORIES or time.monotonic() > deadline:
            break
        directory = pending.popleft()
        children = []
        # Unlike os.walk, scandir lets a huge flat directory stop before its
        # entire listing has been allocated. Skipped entries count too.
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > MAX_VISITED_ENTRIES or time.monotonic() > deadline:
                        return candidates
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if exclusion_reason(relative) or entry.is_symlink() or path.is_junction():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() not in OUTPUT_DIRECTORIES:
                            children.append(path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    try:
                        project_file(root, relative)
                    except (HarnessError, OSError):
                        continue
                    candidates.append(relative)
                    if len(candidates) >= MAX_CANDIDATES:
                        return candidates
        except OSError:
            continue
        pending.extend(sorted(children))
    return candidates


def _git_ignored(root: Path, candidates: list[str]) -> set[str]:
    """Ask Git about only our bounded candidates; do not implement ignore syntax."""
    if not candidates:
        return set()
    try:
        result = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin", "-z"],
            input="\0".join(candidates).encode("utf-8") + b"\0", capture_output=True, timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode not in (0, 1):
            return set()
        return set(result.stdout.decode("utf-8", errors="replace").rstrip("\0").split("\0"))
    except (OSError, subprocess.TimeoutExpired):
        return set()


def _declarations(suffix: str, content: str) -> str:
    names: list[str] = []
    if suffix == ".py":
        for node in ast.parse(content).body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(("class " if isinstance(node, ast.ClassDef) else "def ") + node.name)
                if isinstance(node, ast.ClassDef):
                    names.extend(node.name + "." + child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"))
    elif suffix in {".md", ".markdown"}:
        names = [line.strip()[:100] for line in content.splitlines() if re.match(r"^#{1,3}\s", line)]
    else:
        pattern = r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:declare\s+)?(class|function|interface|type|const|let)\s+([\w$]+)"
        names = [kind + " " + name for kind, name in re.findall(pattern, content, re.MULTILINE)]
    # JSON escaping prevents a filename/heading from changing the block shape.
    return ", ".join(json.dumps(name, ensure_ascii=False) for name in names[:10])[:600]
