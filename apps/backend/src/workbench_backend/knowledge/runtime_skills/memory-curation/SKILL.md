---
name: memory-curation
description: Propose a concise durable memory change for an explicit remember/update request or permitted durable proposal, distinguishing pending from saved. Skip routine task completion and transient logs.
required-tools: [propose_memory]
---

Decide whether the fact is stable and useful beyond this turn. Prefer project scope for repository-specific facts. Inspect a selected existing entry when available to avoid duplication; use its exact base version for updates.

Propose a concise change through propose_memory. Report whether it remains pending, was rejected or actually saved. Do not store credentials, personal transcripts or temporary errors. Automatic saving remains the destination's separate backend policy.

Read references/versions.md for version and scope rules. This skill never changes memory policy, installs a second memory writer or treats a proposal as an applied saved version.
