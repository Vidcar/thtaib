"""Read inert skill packages without extracting archives or executing resources."""

from __future__ import annotations

import re
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

import yaml

from workbench_backend.errors import KnowledgeError

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_FILES = 1024
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
SKILL_FRONTMATTER = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def parse_skill_markdown(markdown: str) -> tuple[str, str]:
    """Validate a native SKILL.md without rewriting its frontmatter or body."""
    match = SKILL_FRONTMATTER.match(markdown)
    try:
        metadata = yaml.safe_load(match.group(1)) if match else None
    except yaml.YAMLError as exc:
        raise KnowledgeError("SKILL.md must have valid YAML frontmatter.", code="skill_frontmatter_invalid", status_code=400) from exc
    if not isinstance(metadata, dict):
        raise KnowledgeError("SKILL.md needs YAML frontmatter with a name and description.", code="skill_frontmatter_invalid", status_code=400)
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or SKILL_NAME.fullmatch(name) is None or len(name) > 64:
        raise KnowledgeError("SKILL.md name must be lowercase letters, digits and single hyphens, at most 64 characters.", code="skill_frontmatter_invalid", status_code=400)
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise KnowledgeError("SKILL.md needs a nonempty description of at most 1024 characters.", code="skill_frontmatter_invalid", status_code=400)
    if not markdown[match.end():].strip():
        raise KnowledgeError("SKILL.md needs instructions after its frontmatter.", code="skill_body_missing", status_code=400)
    return name, description


def safe_resource_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise KnowledgeError("Skill resources must use safe relative paths.", code="skill_path_invalid", status_code=400)
    for part in path.parts:
        if any(ord(char) < 32 or char in '<>:"|?*' for char in part) or part.endswith((".", " ")) or part.split(".")[0].casefold() in RESERVED:
            raise KnowledgeError("A skill resource has an unsafe Windows filename.", code="skill_path_invalid", status_code=400)
    return path.as_posix()


def read_skill_package(source: Path) -> tuple[str, dict[str, bytes]]:
    source = source.expanduser().absolute()
    if source.is_symlink() or source.is_junction():
        raise KnowledgeError("Skill packages cannot be imported through filesystem links.", code="skill_link_denied", status_code=400)
    files: dict[str, bytes] = {}
    names = set()
    total = 0

    def add(path: str, data: bytes):
        nonlocal total
        path = safe_resource_path(path)
        key = unicodedata.normalize("NFC", path).casefold()
        if key in names:
            raise KnowledgeError("Skill resources collide on Windows.", code="skill_path_collision", status_code=400)
        names.add(key)
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_PACKAGE_BYTES or len(files) >= MAX_PACKAGE_FILES:
            raise KnowledgeError("The skill package exceeds the local import size limit.", code="skill_package_too_large", status_code=413)
        files[path] = data

    try:
        if source.is_dir():
            root = source.resolve()
            for child in source.rglob("*"):
                if child.is_symlink() or child.is_junction() or not child.resolve().is_relative_to(root):
                    raise KnowledgeError("Skill packages cannot contain filesystem links.", code="skill_link_denied", status_code=400)
                if child.is_file():
                    with child.open("rb") as stream:
                        add(child.relative_to(source).as_posix(), stream.read(MAX_FILE_BYTES + 1))
        elif source.is_file() and source.suffix.lower() == ".zip":
            with zipfile.ZipFile(source) as archive:
                members = archive.infolist()
                if len(members) > MAX_PACKAGE_FILES * 2:
                    raise KnowledgeError("The skill archive has too many members.", code="skill_package_too_large", status_code=413)
                for member in members:
                    safe_resource_path(member.filename.rstrip("/"))
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode) or mode & 0o170000 not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise KnowledgeError("Skill archives cannot contain links or special files.", code="skill_link_denied", status_code=400)
                    if member.is_dir():
                        continue
                    if member.file_size > MAX_FILE_BYTES:
                        raise KnowledgeError("A skill resource is too large.", code="skill_package_too_large", status_code=413)
                    with archive.open(member) as stream:
                        add(member.filename, stream.read(MAX_FILE_BYTES + 1))
        elif source.is_file() and source.name == "SKILL.md":
            with source.open("rb") as stream:
                add("SKILL.md", stream.read(MAX_FILE_BYTES + 1))
        else:
            raise KnowledgeError("Choose a skill directory, SKILL.md file or ZIP archive.", code="skill_package_missing", status_code=400)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise KnowledgeError(f"The skill package could not be read: {exc}", code="skill_package_unreadable", status_code=400) from exc
    if "SKILL.md" not in files:
        candidates = [name for name in files if name.endswith("/SKILL.md")]
        if len(candidates) == 1:
            prefix = candidates[0][:-len("SKILL.md")]
            if all(name.startswith(prefix) for name in files):
                files = {name[len(prefix):]: data for name, data in files.items()}
    if "SKILL.md" not in files:
        raise KnowledgeError("A skill package must contain SKILL.md at its root.", code="skill_markdown_missing", status_code=400)
    paths = {unicodedata.normalize("NFC", name).casefold() for name in files}
    for name in paths:
        if any(str(parent) in paths for parent in PurePosixPath(name).parents if str(parent) != "."):
            raise KnowledgeError("Skill files and directories collide.", code="skill_path_collision", status_code=400)
    try:
        markdown = files["SKILL.md"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeError("SKILL.md must be UTF-8 with valid YAML frontmatter.", code="skill_frontmatter_invalid", status_code=400) from exc
    parse_skill_markdown(markdown)
    return markdown, files
