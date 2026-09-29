---
name: change-impact
description: Trace impact before substantive changes to shared behaviour, ownership or component boundaries. Use for cross-component features and refactors; skip architecture analysis for trivial text or isolated mechanical edits.
---

# Change impact

Establish the smallest justified change boundary using the project's instructions, current contracts and verification entry point. Inspect the current checkout and existing implementation before proposing another owner.

Follow the affected user action or caller through its owner, inputs, dependencies and outputs to an observable result. Include failure and recovery paths where they affect that result. Identify consumers beyond the edited file, including shared records and contracts. Distinguish intentional snapshots, caches, projections and different operations from competing authorities; matching names or similar code do not establish duplication.

Keep a short conclusion in the current task or existing change record: owner and relevant callers, behaviour to preserve or change, uncertainties that matter, and proportionate acceptance checks. Read only the needed contracts and interfaces. Resolve routine choices independently within the user's authorization. A material unresolved behaviour decision needs clarification; a complete repository map does not.

Use the project's change process when needed. This analysis supports implementation; it does not create an extra approval gate or planning document.
