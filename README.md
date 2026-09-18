# Local AI Workbench — architecture specification pack

Start here as a maintainer. Coding agents start at [AGENTS.md](AGENTS.md).

This pack turns **Starter Specification revision 0.5, dated 18 September 2026**, into repository specifications and a maintenance process. It covers framework ownership, integration boundaries, contracts, execution policy, persistence and verification. It does not redesign the product or prescribe its visual design.

The existing stack is retained. New governance and contract-authoring conventions are labelled as proposals, not attributed to revision 0.5. The [source register](specs/sources/README.md) records provenance and preserves the original document.

**No application repository was inspected. No application behaviour is marked as verified.** This is a specification and governance pack, not an application implementation.

## Put it in your repository

1. Extract this folder and copy its **contents** to the repository root. In an existing repository, merge conflicting files deliberately; do not overwrite existing agent instructions, workflows or documentation without review. Keep the source archive under `specs/sources/`.
2. Read [the specification index](specs/README.md), [architecture](specs/architecture.md) and [adoption decision](specs/decisions/ADR-0001-adopt-specification-pack.md). Review the separately identified [contract-authoring proposal](specs/decisions/ADR-0002-contract-authoring.md).
3. Follow [repository setup](specs/repository-setup.md) to name the human reviewers, activate CODEOWNERS, set repository protections and record approval. One adoption pull request can approve the initial pack; there is no need to approve every file separately.
4. Give the next implementation agent `AGENTS.md`. Its first job is to inspect the actual repository and bind real paths and commands using [the repository map](specs/repository-map.json), not to assume a scaffold exists.

Until the adoption review is recorded, `baseline` specifications preserve the supplied design and `draft` documents are proposals. Producing this pack has not configured any repository permissions or approved changes on your behalf.

## Check the pack locally

From the repository root, with Python 3.11 or newer:

```text
python scripts/check_specs.py
python -m unittest discover -s tests/specs -p "test_*.py"
```

On Windows, `py -3` can replace `python` when that is how your Python installation is exposed. These commands need no third-party Python packages. Their canonical reference is [commands](specs/commands.md).

The supplied workflow runs those checks on Windows and Linux. A passing check establishes **specification integrity**, not working inference, secure isolation, correct agent behaviour or a protected GitHub repository.

## Main entry points

| Need | Open |
| --- | --- |
| Agent working rules and reading order | [AGENTS.md](AGENTS.md) |
| Current architecture and focused module specifications | [Specification index](specs/README.md) |
| How to change specifications without silent drift | [Governance](specs/governance.md) |
| Decisions that remain genuinely unresolved | [Open questions](specs/open-questions.md) |
| Implementation claims and supporting evidence | [Catalogue](specs/catalog.json) and [verification guide](specs/verification.md) |
| Safe adoption into a new or existing repository | [Repository setup](specs/repository-setup.md) |

Do not maintain a second editable Word specification or an agent-specific copy of the rules. Link back to these files. Use Git history for previous versions and decision records for rationale.
