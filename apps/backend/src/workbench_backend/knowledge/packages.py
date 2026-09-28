"""Read inert skill packages without extracting archives or executing resources."""

from __future__ import annotations

import re
import json
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

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
    parse_skill_requirements(markdown)
    return name, description


def parse_skill_requirements(markdown: str) -> dict[str, Any]:
    """Dependency declarations describe readiness; they never confer permissions."""
    match = SKILL_FRONTMATTER.match(markdown)
    try:
        metadata = yaml.safe_load(match.group(1)) if match else None
    except yaml.YAMLError as exc:
        raise KnowledgeError("SKILL.md must have valid YAML frontmatter.", code="skill_frontmatter_invalid", status_code=400) from exc
    if not isinstance(metadata, dict):
        raise KnowledgeError("SKILL.md needs YAML frontmatter.", code="skill_frontmatter_invalid", status_code=400)
    result: dict[str, Any] = {}
    for native, field in (("required-tools", "required_tools"), ("required-connections", "required_connections")):
        value = metadata.get(native, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in value):
            raise KnowledgeError(f"{native} must be a list of nonempty tool names or connection IDs.", code="skill_requirements_invalid", status_code=400)
        result[field] = list(dict.fromkeys(value))
    project = metadata.get("requires-project", False)
    if not isinstance(project, bool):
        raise KnowledgeError("requires-project must be true or false.", code="skill_requirements_invalid", status_code=400)
    result["requires_project"] = project
    return result


def guided_skill_source(markdown: str, fields: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Patch native scalar spans; leave other YAML, comments and resources alone."""
    match = SKILL_FRONTMATTER.match(markdown)
    if match is None:
        raise KnowledgeError("Open Source and add SKILL.md frontmatter.", code="skill_frontmatter_invalid", status_code=400)
    try:
        document = yaml.compose(match.group(1), Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise KnowledgeError("Open Source and correct the YAML frontmatter.", code="skill_frontmatter_invalid", status_code=400) from exc
    if not isinstance(document, yaml.MappingNode):
        raise KnowledgeError("Open Source and use a YAML mapping for frontmatter.", code="skill_frontmatter_invalid", status_code=400)
    pairs: dict[str, yaml.Node] = {}
    keys: set[str] = set()
    for key, value in document.value:
        if not isinstance(key, yaml.ScalarNode) or key.value in keys:
            raise KnowledgeError("Duplicate or complex YAML keys require Source editing.", code="skill_guided_unavailable", status_code=400)
        keys.add(key.value)
        if key.value in {"name", "description"}:
            raw = match.group(1)[value.start_mark.index:value.end_mark.index]
            if not isinstance(value, yaml.ScalarNode) or value.tag != "tag:yaml.org,2002:str" or value.start_mark.index < key.end_mark.index or raw.startswith(("&", "*")):
                raise KnowledgeError("Name and description must be plain text fields; edit this source directly.", code="skill_guided_unavailable", status_code=400)
            pairs[key.value] = value
        elif key.value in {"required-tools", "required-connections", "requires-project"}:
            raw = match.group(1)[value.start_mark.index:value.end_mark.index]
            if value.start_mark.index < key.end_mark.index or raw.startswith(("&", "*")):
                raise KnowledgeError("Shared YAML dependency values require Source editing.", code="skill_guided_unavailable", status_code=400)
            pairs[key.value] = value
    if not {"name", "description"}.issubset(pairs):
        raise KnowledgeError("Open Source and add name and description fields.", code="skill_guided_unavailable", status_code=400)
    current = {"name": pairs["name"].value, "description": pairs["description"].value, "instructions": markdown[match.end():], **parse_skill_requirements(markdown)}
    if fields is None:
        return markdown, current
    patches = []
    fields = {**current, **fields}
    offset = match.start(1)
    for key in ("name", "description"):
        if fields[key] != current[key]:
            node = pairs[key]
            original = markdown[offset + node.start_mark.index:offset + node.end_mark.index]
            suffix = "\r\n" if original.endswith("\r\n") else "\n" if original.endswith("\n") else ""
            patches.append((offset + node.start_mark.index, offset + node.end_mark.index, json.dumps(fields[key], ensure_ascii=False) + suffix))
    if fields["instructions"] != current["instructions"]:
        patches.append((match.end(), len(markdown), fields["instructions"]))
    additions = []
    for native, field in (("required-tools", "required_tools"), ("required-connections", "required_connections"), ("requires-project", "requires_project")):
        if fields[field] == current[field]:
            continue
        rendered = json.dumps(fields[field], ensure_ascii=False)
        if native in pairs:
            node = pairs[native]
            original = markdown[offset + node.start_mark.index:offset + node.end_mark.index]
            suffix = "\r\n" if original.endswith("\r\n") else "\n" if original.endswith("\n") else ""
            patches.append((offset + node.start_mark.index, offset + node.end_mark.index, rendered + suffix))
        else:
            additions.append(f"{native}: {rendered}")
    if additions:
        newline = "\r\n" if "\r\n" in markdown else "\n"
        patches.append((match.end(1), match.end(1), newline + newline.join(additions)))
    for start, end, replacement in sorted(patches, reverse=True):
        markdown = markdown[:start] + replacement + markdown[end:]
    return markdown, {**fields, **parse_skill_requirements(markdown)}


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
