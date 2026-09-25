# Design

## Context

The parent run already owns frozen helper snapshots and durable child-run records, while Chat consumes the upstream-compatible interaction stream. Today the helper is registered after model reservation, its nested public events lack the child-run namespace, and the desktop hides the parent `task` call. Browser request capture recursively scans the tool schema before transport; a nested JSON Schema property named `type` can be a dictionary. Browser and Windows controls currently appear in both Setup and the composer menu.

## Goals / Non-Goals

**Goals:** Make delegation visible from call start through replay, keep each child's public output scoped, make browser-enabled Send predictable, and give each visual capability one compact control home.

**Non-Goals:** Expose private model reasoning, create a second agent runtime or event API, infer ownership of old ambiguous child events, or change Windows grants when merely selecting its tools.

## Decisions

- Use the native parent `task` call ID and its frozen `subagent_type` and `description` as the delegation identity, label and exact request. Register a deterministic child activity before reserving the model; on an early failure settle that activity even when no child run was admitted. This avoids a second prompt field and makes the wait visible.
- Observe the one child execution with the framework's event stream and forward public child events through the existing interaction observer under the child's unique stored namespace. Preserve message and tool IDs and the normal approval/resume path. Do not attribute generic historical `tools` events to a child because parallel calls cannot be distinguished there.
- Merge early stream delegation records with authoritative child-run snapshots by tool-call ID in the rail. The main feed renders one compact delegation line and suppresses raw helper results; a selected rail item uses scoped selectors for the full public child transcript. Reopen loads the saved snapshot and scoped event log. The rail stays closed until selected.
- Guard request-media redaction with a string type check. Reuse existing Browser worker/session status and error codes in the shared readiness and Send preflight; readiness only inspects status and never starts a worker.
- Keep Browser tool intention in `presented_tools` and Windows authorization in `desktop_access` plus the existing live grant. Move their detailed controls into one bounded composer menu, mount runtime polling only while it is open, and route known readiness recovery to the relevant row. Remove incidental frontend `read_file` selection; the backend already adds it to active capture routes. Preserve independent project and knowledge file access.

## Risks / Trade-offs

- Old generic child events may lack a safe owner → show a labelled incomplete historical transcript with saved child status instead of assigning output speculatively.
- A late child event or reconnect may arrive after a status snapshot → merge by stable call/run IDs, accept only the owning conversation and generation, and test live and reopened projections.
- Moving controls into a popover could hide recovery or clip narrow windows → keep the row status visible, focus the relevant row on recovery, bound and scroll the menu, and test keyboard and narrow layouts.
- Worker installation or Windows grant may change after preview → recheck at Send and at tool dispatch; refresh readiness when install, reset, close, grant or revocation succeeds.

## Migration Plan

No persistent data migration or new endpoint is required. Existing saved conversations and grants retain their current meaning. Scoped events improve new helper runs; older ambiguous logs retain truthful status with an incomplete-detail label. Rollback restores the previous renderer/backend build without rewriting saved data.
