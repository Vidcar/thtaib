#!/usr/bin/env python3
"""Read-only, standard-library integrity checks for the specification pack.

Validates links, requirement IDs, catalogue and repository-map shape, file
pointers, the archived source hash and evidence-row shape. It does not run
tests, judge semantics or inspect GitHub settings; see specs/verification.md.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import unquote, urlsplit

CORE_FILES = (
    "README.md", "AGENTS.md", "thtaib-vision.md",
    "specs/README.md", "specs/architecture.md", "specs/contracts.md",
    "specs/catalog.json", "specs/repository-map.json", "specs/commands.md",
    "specs/verification.md", "scripts/check_specs.py", "tests/specs/test_check_specs.py",
)
ROOT_MARKDOWN_FILES = ("README.md", "AGENTS.md", "HANDOVER.md", "thtaib-vision.md", ".github/pull_request_template.md")
MAINTAINED_MARKDOWN_DIRS = ("specs", "docs")
SCHEMA_VERSION = 2
ID_PATTERN = r"[A-Z]{2,8}-\d{3}"
ID_RE = re.compile(rf"\b({ID_PATTERN})\b")
DEFINITION_RE = re.compile(rf"^### ({ID_PATTERN}): [^\n]+", re.M)
BLOCK_RE = re.compile(
    rf'(?P<block><a id="(?P<anchor>[a-z0-9-]+)"></a>\n'
    rf'### (?P<id>{ID_PATTERN}): [^\n]+\n.*?)(?=\n<a id=|\n## |\Z)',
    re.M | re.S,
)
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^\n)]+)\)")
PLACEHOLDER_RE = re.compile(r"REPLACE_WITH|YOUR_[A-Z]", re.I)
HEX_ID_RE = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
NON_REQUIREMENT_IDS = {"SHA-256", "SHA-512"}
DOC_STATUSES = {"accepted", "draft", "superseded", "informational"}
DOC_KINDS = {"guide", "specification", "decision", "source", "reference", "template"}
IMPL_STATUSES = {"planned", "built", "verified", "retired"}
EVIDENCE_KINDS = {"ci-smoke", "uat", "manual"}
VERIFYING_KINDS = {"ci-smoke", "uat"}
EVIDENCE_RESULTS = {"passed", "failed", "skipped"}


def without_fences(text: str) -> str:
    """Blank fenced examples so example IDs and links are not treated as live."""
    output: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    for line in text.splitlines():
        opening = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if fence_char is None:
            if opening:
                fence_char = opening.group(1)[0]
                fence_length = len(opening.group(1))
                output.append(" " * len(line))
            else:
                output.append(line)
        else:
            if re.match(rf"^\s*{re.escape(fence_char)}{{{fence_length},}}\s*$", line):
                fence_char = None
            output.append(" " * len(line))
    return "\n".join(output) + "\n"


def anchors(text: str) -> set[str]:
    clean = without_fences(text)
    result = set(re.findall(r'<a\s+id="([^"]+)"\s*></a>', clean))
    seen: Counter[str] = Counter()
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", clean, re.M):
        heading = re.sub(r"<[^>]+>", "", match.group(1)).replace("`", "")
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        suffix = f"-{seen[slug]}" if seen[slug] else ""
        result.add(slug + suffix)
        seen[slug] += 1
    return result


def requirement_blocks(text: str) -> dict[str, str]:
    normalised = text.replace("\r\n", "\n")
    return {m.group("id"): normalised[m.start("block"):m.end("block")].strip() + "\n"
            for m in BLOCK_RE.finditer(without_fences(normalised))}


def requirement_digest(block: str) -> str:
    return hashlib.sha256(block.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)


def valid_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_RE.search(value)


def is_url(value: Any) -> bool:
    return isinstance(value, str) and urlsplit(value).scheme in {"http", "https"} and bool(urlsplit(value).netloc)


def root_path(root: Path, value: Any, errors: list[str], label: str,
              kind: str = "file") -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value:
        errors.append(f"{label}: use a nonempty repository-relative forward-slash path")
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in value or "#" in value:
        errors.append(f"{label}: unsafe or noncanonical repository path: {value}")
        return None
    target = (root / candidate).resolve()
    if not target.is_relative_to(root.resolve()):
        errors.append(f"{label}: path escapes the repository: {value}")
        return None
    exists = target.is_dir() if kind == "directory" else target.is_file()
    if not exists:
        errors.append(f"{label}: missing {kind}: {value}")
        return None
    return target


def exact_keys(obj: dict[str, Any], keys: set[str], errors: list[str], label: str) -> None:
    if set(obj) != keys:
        errors.append(f"{label}: expected keys {sorted(keys)}; received {sorted(obj)}")


def markdown_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for directory in MAINTAINED_MARKDOWN_DIRS:
        path = root / directory
        if path.is_dir():
            files.update(path.rglob("*.md"))
    for name in ROOT_MARKDOWN_FILES:
        path = root / name
        if path.is_file():
            files.add(path)
    return sorted(files)


def check_markdown_links(root: Path, texts: dict[str, str], errors: list[str]) -> None:
    anchor_cache = {name: anchors(text) for name, text in texts.items()}
    for name, text in texts.items():
        for match in LINK_RE.finditer(without_fences(text)):
            raw = match.group(1).strip().split(' "', 1)[0].strip("<>")
            try:
                parsed = urlsplit(raw)
            except ValueError:
                errors.append(f"{name}: malformed link: {raw}")
                continue
            if parsed.scheme in {"http", "https", "mailto", "tel"} or parsed.netloc:
                continue  # Deliberately no external-network checks.
            if parsed.scheme or "\\" in parsed.path or parsed.path.startswith("/"):
                errors.append(f"{name}: unsupported local link format: {raw}")
                continue
            path = unquote(parsed.path)
            target = ((root / name).parent / path).resolve() if path else (root / name).resolve()
            if not target.is_relative_to(root.resolve()):
                errors.append(f"{name}: local link escapes the repository: {raw}")
                continue
            if not target.exists():
                errors.append(f"{name}: broken local link: {raw}")
                continue
            if parsed.fragment and target.suffix.lower() == ".md":
                key = target.relative_to(root.resolve()).as_posix()
                if key not in anchor_cache:
                    anchor_cache[key] = anchors(target.read_text(encoding="utf-8"))
                if unquote(parsed.fragment) not in anchor_cache[key]:
                    errors.append(f"{name}: missing Markdown anchor: {raw}")


def compare_baseline(root: Path, base_ref: str, current_ids: set[str]) -> list[str]:
    """Catch requirement deletion even when both current text and catalogue vanish."""
    if not HEX_ID_RE.fullmatch(base_ref):
        return ["base-ref: supply a full Git commit/object ID, not a branch expression"]

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=root, text=True,
                              capture_output=True, timeout=15, check=False)
    try:
        present = git("cat-file", "-e", f"{base_ref}^{{commit}}")
        if present.returncode:
            return ["base-ref: commit is unavailable; fetch the base history before checking"]
        tree = git("ls-tree", "--name-only", base_ref, "--", "specs/catalog.json")
        if tree.returncode:
            return ["base-ref: could not inspect the base tree"]
        if not tree.stdout.strip():
            return []  # No earlier catalogue exists.
        previous = git("show", f"{base_ref}:specs/catalog.json")
        if previous.returncode:
            return ["base-ref: could not read the previous catalogue"]
        data = json.loads(previous.stdout, object_pairs_hook=_unique_pairs)
        old_ids = {row["id"] for row in data["requirements"]}
        removed = old_ids - current_ids
        return (["base-ref: requirement IDs disappeared; retain/retire them: " +
                 ", ".join(sorted(removed))] if removed else [])
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError) as exc:
        return [f"base-ref: failed to compare the prior catalogue: {exc}"]


def check_adoption(root: Path, catalog: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    adoption = catalog.get("adoption")
    if not isinstance(adoption, dict):
        errors.append("adoption: expected an object")
        return {}
    exact_keys(adoption, {"state", "decision"}, errors, "adoption")
    if adoption.get("state") not in {"pending", "accepted"}:
        errors.append("adoption: state must be pending or accepted")
    root_path(root, adoption.get("decision"), errors, "adoption decision")
    return adoption


def check_documents(root: Path, catalog: dict[str, Any], texts: dict[str, str],
                    adoption: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    documents = catalog.get("documents")
    if not isinstance(documents, list):
        errors.append("documents: expected a list")
        documents = []
    doc_by_path: dict[str, dict[str, Any]] = {}
    for row in documents:
        if not isinstance(row, dict):
            errors.append("document entry: expected an object")
            continue
        exact_keys(row, {"path", "kind", "status"}, errors, "document entry")
        path = row.get("path")
        root_path(root, path, errors, "catalogue document")
        if not isinstance(path, str):
            continue
        if path in doc_by_path:
            errors.append(f"duplicate document registration: {path}")
        doc_by_path[path] = row
        if not path.startswith("specs/") or not path.endswith(".md"):
            errors.append(f"catalogue document must be Markdown under specs/: {path}")
        if row.get("kind") not in DOC_KINDS:
            errors.append(f"document {path}: invalid kind")
        if row.get("status") not in DOC_STATUSES:
            errors.append(f"document {path}: invalid status")
        if row.get("status") == "informational" and row.get("kind") in {"specification", "decision"}:
            errors.append(f"document {path}: specifications and decisions cannot be informational")
    if adoption.get("state") == "accepted" and doc_by_path.get(adoption.get("decision"), {}).get("status") != "accepted":
        errors.append("adoption: the adoption decision itself must be accepted in the catalogue")
    for path in texts:
        is_report = path.startswith("specs/evidence/") and path != "specs/evidence/README.md"
        if path.startswith("specs/") and not is_report and path not in doc_by_path:
            errors.append(f"unregistered specification document: {path}")
    return doc_by_path


def check_definitions(texts: dict[str, str], doc_by_path: dict[str, dict[str, Any]],
                      errors: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    definitions: dict[str, str] = {}
    blocks: dict[str, str] = {}
    for path, text in texts.items():
        clean = without_fences(text)
        local_blocks = requirement_blocks(text)
        for match in BLOCK_RE.finditer(clean):
            if match.group("anchor") != match.group("id").lower():
                errors.append(f"{path}: requirement anchor must match {match.group('id').lower()}")
        for rid in DEFINITION_RE.findall(clean):
            if rid in definitions:
                errors.append(f"duplicate requirement definition: {rid}")
            definitions[rid] = path
            if rid not in local_blocks:
                errors.append(f"{path}: {rid} needs the required explicit anchor/block format")
            else:
                blocks[rid] = local_blocks[rid]
                if "**Acceptance:**" not in local_blocks[rid]:
                    errors.append(f"{path}: {rid} has no acceptance check")
            if doc_by_path.get(path, {}).get("kind") != "specification":
                errors.append(f"{path}: normative requirement {rid} is outside a registered specification")
    for path, text in texts.items():
        for rid in set(ID_RE.findall(without_fences(text))):
            if rid.startswith(("OQ-", "DEV-", "ADR-")) or rid in NON_REQUIREMENT_IDS:
                continue
            if rid not in definitions:
                errors.append(f"{path}: unknown requirement reference: {rid}")
    return definitions, blocks


def check_evidence(root: Path, rid: str, status: str, evidence: list[Any],
                   block: str | None, verifiable_by: set[str], errors: list[str]) -> bool:
    """Validate evidence rows; return whether one row can support `verified`."""
    supports_verified = False
    for item in evidence:
        if not isinstance(item, dict):
            errors.append(f"{rid}: evidence entry must be an object")
            continue
        exact_keys(item, {"kind", "ref", "commit", "date", "environment", "result", "requirement_sha256"},
                   errors, f"{rid} evidence")
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            errors.append(f"{rid}: evidence kind must be one of {sorted(EVIDENCE_KINDS)}")
        ref = item.get("ref")
        report: Path | None = None
        if not is_url(ref):
            report = root_path(root, ref, errors, f"{rid} evidence ref")
        if not HEX_ID_RE.fullmatch(str(item.get("commit", ""))):
            errors.append(f"{rid}: evidence requires a full tested Git object ID")
        try:
            date.fromisoformat(str(item.get("date")))
        except (TypeError, ValueError):
            errors.append(f"{rid}: evidence date must be ISO YYYY-MM-DD")
        if not valid_text(item.get("environment")):
            errors.append(f"{rid}: evidence environment is empty or a placeholder")
        result = item.get("result")
        if result not in EVIDENCE_RESULTS:
            errors.append(f"{rid}: invalid evidence result")
        digest = item.get("requirement_sha256")
        if digest is not None and not (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
            errors.append(f"{rid}: requirement_sha256 must be null or a 64-character hex digest")
        if report and report.suffix == ".md":
            body = report.read_text(encoding="utf-8")
            if not body.strip() or PLACEHOLDER_RE.search(body):
                errors.append(f"{rid}: evidence report must be nonempty Markdown without template placeholders")
        if kind in VERIFYING_KINDS and status == "verified":
            if kind not in verifiable_by:
                errors.append(f"{rid}: {kind} evidence cannot verify this requirement; allowed tiers: {sorted(verifiable_by)}")
            elif result != "passed":
                errors.append(f"{rid}: verified claim has a non-passing {kind} row; downgrade to built")
            elif digest is None:
                errors.append(f"{rid}: verified claim needs requirement_sha256 on its {kind} row")
            elif block is not None and digest != requirement_digest(block):
                errors.append(f"{rid}: stale evidence; requirement text changed")
            else:
                supports_verified = True
    return supports_verified


def check_requirements(root: Path, catalog: dict[str, Any], definitions: dict[str, str],
                       blocks: dict[str, str], doc_by_path: dict[str, dict[str, Any]],
                       errors: list[str]) -> set[str]:
    requirements = catalog.get("requirements")
    if not isinstance(requirements, list):
        errors.append("requirements: expected a list")
        requirements = []
    registered: set[str] = set()
    for row in requirements:
        if not isinstance(row, dict):
            errors.append("requirement entry: expected an object")
            continue
        exact_keys(row, {"id", "document", "status", "verifiable_by", "code", "tests", "evidence"}, errors, "requirement entry")
        rid = row.get("id")
        if not isinstance(rid, str) or not re.fullmatch(ID_PATTERN, rid) or rid.startswith(("OQ-", "DEV-", "ADR-")):
            errors.append("requirement entry: invalid requirement ID")
            continue
        if rid in registered:
            errors.append(f"duplicate catalogue requirement: {rid}")
        registered.add(rid)
        if definitions.get(rid) != row.get("document"):
            errors.append(f"{rid}: catalogue document does not match its unique definition")
        status = row.get("status")
        if status not in IMPL_STATUSES:
            errors.append(f"{rid}: invalid status")
        tiers = row.get("verifiable_by")
        if not isinstance(tiers, list) or not tiers or not set(tiers) <= VERIFYING_KINDS or len(set(tiers)) != len(tiers):
            errors.append(f"{rid}: verifiable_by must be a nonempty list drawn from {sorted(VERIFYING_KINDS)}")
            tiers = []
        for category in ("code", "tests"):
            values = row.get(category)
            if not isinstance(values, list):
                errors.append(f"{rid}: {category} must be a list of real file paths")
            else:
                for value in values:
                    root_path(root, value, errors, f"{rid} {category}")
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{rid}: evidence must be a list")
            evidence = []
        supports = check_evidence(root, rid, str(status), evidence, blocks.get(rid), set(tiers), errors)
        if status == "verified":
            if doc_by_path.get(row.get("document"), {}).get("status") != "accepted":
                errors.append(f"{rid}: verified claims require an accepted specification")
            if not row.get("code") or not row.get("tests"):
                errors.append(f"{rid}: verified claim needs code and tests pointers")
            if not supports:
                errors.append(f"{rid}: verified claim needs a passing {' or '.join(sorted(tiers) or ['uat'])} evidence row with a matching digest")
    for rid in sorted(set(definitions) - registered):
        errors.append(f"requirement missing from catalogue: {rid}")
    if not definitions:
        errors.append("no normative requirements found")
    return registered


def check_bindings(root: Path, mapping: dict[str, Any], doc_by_path: dict[str, dict[str, Any]],
                   errors: list[str]) -> None:
    bindings = mapping.get("bindings")
    if not isinstance(bindings, list):
        errors.append("repository map: bindings must be a list")
        return
    binding_ids: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            errors.append("repository binding: expected an object")
            continue
        exact_keys(binding, {"id", "state", "path", "kind", "owner_spec", "required_before"}, errors, "repository binding")
        bid = binding.get("id")
        if not valid_text(bid):
            errors.append("repository binding: missing id")
            continue
        if bid in binding_ids:
            errors.append(f"duplicate repository binding: {bid}")
        binding_ids.add(bid)
        if binding.get("kind") not in {"file", "directory"}:
            errors.append(f"binding {bid}: kind must be file or directory")
        if binding.get("owner_spec") not in doc_by_path or not valid_text(binding.get("required_before")):
            errors.append(f"binding {bid}: needs a registered owning specification and blocking point")
        if binding.get("state") == "unbound":
            if binding.get("path") is not None:
                errors.append(f"binding {bid}: unbound path must be null, not a guessed location")
        elif binding.get("state") == "bound":
            root_path(root, binding.get("path"), errors, f"binding {bid}", kind=binding.get("kind", "file"))
        else:
            errors.append(f"binding {bid}: state must be bound or unbound")


def validate_repo(root: Path, *, base_ref: str | None = None) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for path in CORE_FILES:
        root_path(root, path, errors, "required pack file")
    try:
        catalog = load_json(root / "specs/catalog.json")
        mapping = load_json(root / "specs/repository-map.json")
    except (OSError, ValueError) as exc:
        return errors + [f"manifest read failed: {exc}"]
    if not isinstance(catalog, dict) or not isinstance(mapping, dict):
        return errors + ["catalogue and repository map must be JSON objects"]
    exact_keys(catalog, {"schema_version", "adoption", "source_archive", "documents", "requirements"}, errors, "catalogue")
    exact_keys(mapping, {"schema_version", "bindings"}, errors, "repository map")
    if catalog.get("schema_version") != SCHEMA_VERSION or mapping.get("schema_version") != 1:
        errors.append(f"unsupported manifest schema_version (catalogue {SCHEMA_VERSION}, repository map 1)")

    texts: dict[str, str] = {}
    for path in markdown_files(root):
        if not path.resolve().is_relative_to(root):
            errors.append(f"Markdown file escapes root through a symlink: {path}")
            continue
        try:
            texts[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read Markdown {path}: {exc}")
    check_markdown_links(root, texts, errors)

    adoption = check_adoption(root, catalog, errors)

    archive = catalog.get("source_archive")
    if not isinstance(archive, dict):
        errors.append("source_archive: expected an object")
    else:
        exact_keys(archive, {"path", "sha256"}, errors, "source archive")
        archived_path = root_path(root, archive.get("path"), errors, "source archive")
        if not re.fullmatch(r"[0-9a-f]{64}", str(archive.get("sha256", ""))):
            errors.append("source archive: invalid SHA-256")
        elif archived_path and hashlib.sha256(archived_path.read_bytes()).hexdigest() != archive["sha256"]:
            errors.append("source archive: SHA-256 mismatch; archived source bytes changed")

    doc_by_path = check_documents(root, catalog, texts, adoption, errors)
    definitions, blocks = check_definitions(texts, doc_by_path, errors)
    registered = check_requirements(root, catalog, definitions, blocks, doc_by_path, errors)
    check_bindings(root, mapping, doc_by_path, errors)
    if base_ref:
        errors.extend(compare_baseline(root, base_ref, registered))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--requirement-hash", metavar="ID")
    parser.add_argument("--base-ref", default=os.environ.get("SPEC_BASE_REF") or None,
                        help="full base commit ID; compare historical requirement IDs (needs Git)")
    args = parser.parse_args(argv)
    try:
        if args.requirement_hash:
            # Stale-evidence errors are expected while obtaining the new digest.
            errors = [e for e in validate_repo(args.root) if ": stale evidence;" not in e]
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            found = []
            for path in markdown_files(args.root.resolve()):
                block = requirement_blocks(path.read_text(encoding="utf-8")).get(args.requirement_hash)
                if block:
                    found.append(block)
            if len(found) != 1:
                print("ERROR: requirement must have exactly one definition", file=sys.stderr)
                return 1
            print(requirement_digest(found[0]))
            return 0
        errors = validate_repo(args.root, base_ref=args.base_ref)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            print(f"FAILED: {len(errors)} specification integrity issue(s).", file=sys.stderr)
            return 1
        catalog = load_json(args.root / "specs/catalog.json")
        mapping = load_json(args.root / "specs/repository-map.json")
        counts = Counter(row["status"] for row in catalog["requirements"])
        evidence_rows = sum(len(row["evidence"]) for row in catalog["requirements"])
        uat_only = sum(row["verifiable_by"] == ["uat"] for row in catalog["requirements"])
        unbound = sum(b["state"] == "unbound" for b in mapping["bindings"])
        print(f"PASS: {len(catalog['documents'])} documents; {len(catalog['requirements'])} requirements; "
              f"{evidence_rows} evidence rows; {unbound} unbound locations; adoption {catalog['adoption']['state']}.")
        print("Requirement status: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
              + f"; uat-only requirements: {uat_only}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(f"ERROR: unable to validate specification data: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
