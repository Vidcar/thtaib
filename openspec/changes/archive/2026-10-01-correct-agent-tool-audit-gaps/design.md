# Design

## Context

See proposal.md. Current main `6e43b44` still has all five reassessment gaps. Native mutations take a per-project `threading.Lock` by waiting on the default executor, then need that same pool to finish. `apply_edits` takes the same lock inside the synchronous tool. The desktop derives Standard tools from a local exclusion list. The evidence-researcher template pins project search. Stock templates omit `read_tool_result` while notices always name it. Connection readiness treats an empty tool list as untested. Active change `consolidate-product-contract` is unrelated and stays untouched.

## Goals / Non-Goals

**Goals:**

- Keep one per-project mutation gate that asynchronous waiters can join without occupying a blocking worker.
- Publish Standard membership, groups and Plan eligibility from the existing catalogue response.
- Admit the existing evidence-researcher template without a project, and keep its project tools when a project is bound.
- Put the retained-result reader on new stock templates that consume retained evidence, and make notices follow the accepted selection.
- Record tested protocol capabilities and use them for readiness.

**Non-Goals:**

- A new agent loop, tool catalogue, connection framework, model setting or whole-task budget.
- Raising worker counts, removing the mutation gate, or serialising every tool.
- Rewriting saved setups, enabling connections, or granting permissions to make a test pass.
- Rewriting the nine runtime skills.

## Decisions

### Awaitable per-project lease, with a synchronous borrow

Replace the object returned by `project_mutation_lock` with a small lease. The short critical section stays a `threading.Lock`. Asynchronous waiters park on a Future and synchronous callers park on an `Event`, both in one FIFO. Releasing the lease transfers ownership to the next waiter and keeps the gate held, so a cancelled waiter cannot open it for two holders.

Middleware awaits that Future directly. It does not submit the wait to the default executor and does not shield the wait. After admission it still rechecks dispatch, cancellation and the saved grant before the effect. Admitted native work and post-effect inspection keep the existing shielded settlement.

`apply_edits` remains inside the tool body. Middleware also admits `apply_edits` on this lease. Both the asynchronous lease and the synchronous tool hook set a `ContextVar` to that same lease, so the inner `with` borrows instead of acquiring again. Direct callers and tests still acquire and stay non-reentrant. A re-entrant lock was rejected because the event-loop holder and the worker thread are different threads.

Queued cancellation removes the waiter. If ownership was already marked under the mutex, that cancelled waiter releases so the gate cannot stick. Cancellation of admitted work still waits for the worker that owns the effect.

### Catalogue projection, not a second registry

`GET /v1/agent-tools` adds group, prerequisites, opt-in, the sixteen Standard context combinations already produced by `resolve_presented_tools(None, ...)`, Plan tool names and the two trusted public-web remote names. The desktop groups and materialises an explicit list only from that payload and only while the catalogue loaded. The applicable context is project-bound when the editor has a project or the agent requires one; knowledge, attachment and capture flags are included only when that surface knows them. Missing catalogue data disables the control that would persist a derived list. Explicit saved lists are reloaded as stored. A short review note appears when an explicit list contains opt-in tools, without claiming the selection was accidental.

### Projectless research uses existing omission rules

The researcher template keeps project read names so a bound project still has them, and stops pinning them. It pins the attachment and retained-result readers. Progressive admission no longer puts unpinned project-file tools back into the executable set when no project is bound. An explicitly selected shell or preview tool stays selected so using it can pause for a project. Pinned blocked tools and always-loaded blocked tools still fail admission. Knowledge-route reads stay available when knowledge routes are selected.

Trusted `search_web` and `read_web_page` operations of an already selected built-in public-web connection are added at admission when tools are not off and the name is not excluded. No connection id is written into the template. Tools off adds nothing. Other MCP tools are not added.

### Notices follow the accepted selection

New applications of all six stock templates include `read_tool_result`. Research, review, browser and Windows templates pin it. The two builders include it and leave it unpinned. Saved setups are not migrated. Retention notices recommend `read_tool_result` when it is accepted, describe `read_file` as the line-oriented fallback when that is the only reader, and state the limitation when neither is accepted.

### Readiness follows the tested capability

`test()` records protocol capabilities from the server capability set plus a real resources list. Method-not-found on resources is unsupported resources, not a failed connection, when tool discovery succeeded. Public web records tools only. Readiness requires a successful test and a recorded capability; an empty tool list is then valid. Legacy records with tools and no capability field stay tool-ready. Legacy empty records stay unready until retested. Resource operations require the resources capability and use a distinct unsupported error. Snapshots do not need the new field; resource checks revalidate the stored record.

## Risks / Trade-offs

- [Lease handoff races with cancellation] → Admit under the mutex before completing the waiter, and release if that waiter is cancelled after admission. Watch the regression from a subprocess.
- [Borrowing could hide a real nested acquire] → Borrow only when the context var is this same lease. Direct acquire stays non-reentrant.
- [Stopping filesystem re-add could drop a tool a projectless run previously executed] → Only unpinned project-file tools are omitted, and only without a project. Selected shell and preview tools stay in the set so use still pauses for a project. Knowledge routes remain. Tests cover pinned rejection, project-bound retention and the existing projectless shell pause.
- [Adding trusted web tools could widen an explicit list] → Only the two remote names, only for an already selected built-in public-web connection, never when tools are off or the name is excluded.
- [A new connection field changes the generated contract] → Optional, default empty, and regenerate the shared contract. Existing nonempty tool records remain ready.

## Migration Plan

No saved-setup rewrite. New templates apply only when a person chooses them again. Connections gain an optional capability list on the next successful test. Rollback is reverting the change; in-flight runs keep their frozen selections. Verify with focused regressions, backend default and integration, desktop build, contract freshness and OpenSpec validation, plus fresh-context review of the lease and selection changes.

## Open Questions

None. The reassessment evidence scripts were not beside the report; the current source was inspected directly.
