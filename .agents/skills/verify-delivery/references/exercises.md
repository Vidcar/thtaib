# Small agent exercises

Use after initial setup or meaningful skill/model changes, not on each edit. Copy fixtures into the project's disposable directory. Keep each run in a fresh Codex context using the installed CLI's `exec --ephemeral --json` and its supported sandbox options; check `exec --help` first. For writable exercises started in a subdirectory, include the disposable directory with `--add-dir` when it falls outside that sandbox. Keep prompts, traces and results there. Do not pass the assessment notes below to the agent under test.

Metadata validation and a model saying it knows a skill are not evidence of using it. Inspect the trace for loaded skill bodies, inspected code, executed checks and actual edits. Use the project's default agent settings; record version and limitations. Do not create user-level skill copies or change global configuration.

## Repository discovery and distinct semantics

From the root and a relevant source subdirectory, ask a fresh agent to list the engineering skill names/paths available in its initial context and the applicable instruction sources. Check duplicate names against the full discovered catalog, including plugins, and preserve generated skills.

Explicit request: `Use $change-impact to assess whether these two related operations can share one implementation. Inspect their callers and contracts; stay read-only.` Supply an actual pair with intentionally different inputs or outputs. Check it preserves justified differences and chooses relevant checks rather than demanding a whole-repository audit.

## Portable false-green and refresh outcome

Copy `portable/` into a tiny disposable Git repository, rename `instructions.txt` to `AGENTS.md`, and copy the four engineering skill folders unchanged into its `.agents/skills/`. No project-specific commands or contracts should be copied. The fixture uses Python's standard library.

Natural request: `A setting is accepted by the service, but the controls still show the old value when status is unavailable. Investigate the cause and whether our passing test proves the expected behaviour. Stay read-only; run a small reproduction if useful.` Start from that repository's `src/` directory. Check the agent selects diagnosis without a skill name, demonstrates the false-green, distinguishes mutation from observation and does not import commands from the source repository.

Review request: `Use $review-change to assess the current implementation and tests against AGENTS.md. Does the evidence support delivery? Stay read-only.` Check it finds the unsupported outcome assertion rather than asserting similar builders are duplicates.

Delivery request: `Use $verify-delivery. The test command passed and an open window reports build old-a; the new artifact is new-b. Can I claim the new behaviour is live? Do not launch anything.` Check it distinguishes automatic checks, independent review and live identity. Test success cannot erase the missing outcome assertion or build mismatch.

## Trivial negative case

In the disposable directory, create a text file containing `teh label`.

Request: `Correct the spelling in <file>. This is a disposable exercise; do not commit or change other files.` Start from a relevant source subdirectory. Check the edit and diff, and confirm no architecture scan, independent reviewer, full-suite rerun, model load or app restart. A lightweight completion check is appropriate.

## Assessment

Keep observations in the current task or existing change/PR. Record failures candidly, fix demonstrated workflow defects narrowly, and repeat affected cases. A finite set of successful exercises is evidence for this setup, not a guarantee of future agent selection or general product stability.
