---
name: project-change
description: Implement or refactor a bounded project change by tracing its owner, preserving contracts and verifying the changed behavior. Use for substantive project work, not factual questions or formatting-only edits.
requires-project: true
required-tools: [read_file]
---

Read the project's entry point and current handover, then the affected contract and owner. Inspect the working tree using selected tools and preserve unrelated changes. Trace the requested outcome through its consumers before choosing the smallest coherent change.

Use native file tools for authorized mutations. Independent reads can run together; dependent writes to a shared file must be sequential across tool batches. Read–edit–test–edit is valid when later edits use fresh evidence. Plan and read-only work must stay usable without shell or write tools.

Choose checks by changed behavior. Inspect the resulting diff and usable outcome, and distinguish implemented from tested and delivered. Read references/workflow.md for evidence and permission rules. Never assume a repository uses thtaib's engineering process.
