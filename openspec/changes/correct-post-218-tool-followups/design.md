# Design

## Context

PR #218 removed shared-executor starvation and stopped the frontend from treating new opt-in tools as Standard. The review of revision `6dc583f` kept that update and left three narrower gaps: projectless research under eager tool-definition loading, MCP resources without `tools/list`, and continuation guidance that ignores the automatic framework reader.

## Goals / Non-Goals

**Goals:**

- Make a loading preference unable to decide whether optional project reads exist.
- Test resources and tools as separate advertised MCP capabilities.
- Make continuation guidance match the reader the model can actually call.

**Non-Goals:**

- Reopening the mutation lease, the backend catalogue projection, or the six template reader selections.
- Rewriting saved setups, retuning models, or migrating the MCP protocol.
- Changing the desktop "N tools ready" label.

## Decisions

1. **Omit unpinned project reads at admission.** `ls`, `read_file`, `glob`, and `grep` stay in the saved researcher selection. Both When needed and Always include all drop the unpinned names when no project is bound. A missing input policy keeps the historical fail-all filesystem check. Pinned names, skill-required names, eager mutations, and eager shell or preview still fail.
2. **A framework-only `read_file` does not satisfy a skill.** Skill checks use the accepted tool set after removing that automatic reader when `read_file` was not selected. Knowledge-route `ls` and `read_file` remain readers for `/memories/` and `/skills/` when those routes are selected. On a projectless run their schema names those virtual routes and does not describe a project root. `glob` and `grep` stay omitted until a project is bound.
3. **Trust negotiated capabilities.** `server_capabilities` is the authority. `None` means the adapter did not expose a result, so the existing list-tools path remains for stubs and public web. An empty set means negotiation completed without tools or resources and the test fails rather than looking ready. Typed method-not-found (`-32601`) is the only unsupported-method signal. Matching error text is not.
4. **Guide from the effective reader.** `continuation_notice` uses `authorized_tool_names`, including framework paths, exclusions, and Tools off. `OwnedToolResults.read` adds `reader_notice` for the current run and does not rewrite the stored notice. An excluded framework reader is hidden and rejected at dispatch.

## Risks / Trade-offs

- A resources-only connection can show "0 tools ready" in the desktop connection list. Readiness is still `last_tested_at` without `last_error`. The label is left unchanged so this patch stays backend-only.
- Deferred unpinned shell stays selected so use can pause. Eager shell still fails. That split is existing behaviour.
- In-process FastMCP and MCPServer cover the protocol branches. This patch does not add a live external MCP transport.

## Migration Plan

No saved-setup rewrite and no protocol migration. Existing empty-manifest, mixed, tools-only, revocation, and changed-version tests stay. Archive this change after the corrective patch is merged.

## Open Questions

None. The review's alternative for R1, context-aware omission of optional project reads, is the selected correction because removing those tools from the template would drop them from project-bound research.
