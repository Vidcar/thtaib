# Design

## Context

See proposal.md. Deep Agents 0.7.19 streams ripgrep JSON with subprocess text mode but no explicit encoding. Windows Python 3.12 defaults to cp1252. The Windows shortcut starts the console script; the documented module and console entrypoints share `__main__.main`. The host shell separately decodes captured bytes using the interpreter's preferred encoding.

## Goals / Non-Goals

Deliver the two affected specification scenarios without copying native search, patching site-packages, changing model settings, or introducing general runtime-exception suppression.

## Decisions

- Launch the shortcut with `python -X utf8 -m workbench_backend`. The common entrypoint checks Windows UTF-8 mode before app import and, when needed, runs the same interpreter once with `-X utf8`, forwarding exact arguments, inherited environment/streams and exit status. A waiting bootstrap is necessary on Windows: exec replacement releases the original process handle and loses child exit status. No environment variables are modified, so host Python commands do not inherit a new encoding policy.
- Use `locale.getencoding()` for host-command captured bytes; it preserves the existing ANSI locale independently of UTF-8 mode. Explicitly encoded worker protocols remain unchanged.
- Extend the shared sync/async error adapter only for UnicodeDecodeError on grep/read_file. Return a status=error ToolMessage with the same identity and bounded original codec diagnostic. Existing outcome recording persists failure/continue; no retry, alternate search implementation or partial-success fabrication is introduced.

## Risks / Trade-offs

- UTF-8 bootstrap introduces a waiting process only for Windows launches without UTF-8 mode. Verify console/module entrypoints, lifecycle, exit status and cancellation cleanup; the normal shortcut starts directly in UTF-8 mode.
- The interpreter default changes for native text protocols. Verify host output separately and preserve explicit encodings.
- In-process test harnesses bypass CLI bootstrap. Real search tests run in explicit UTF-8 child interpreters; recovery tests also inject decoder failures to exercise the safety net.

## Migration Plan

No data migration. Validate default/integration checks and real-model Chat using an isolated root and existing deployment. Sync and archive deltas, merge the reviewed change, and refresh only the established backend after checking for active work. Preserve model residency, desktop, chats and unrelated files. Rollback is the ordinary Git revert and backend refresh; no failed turn is replayed.
