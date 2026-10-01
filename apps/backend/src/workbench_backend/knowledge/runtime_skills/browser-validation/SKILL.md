---
name: browser-validation
description: Test a requested web flow or responsive layout using current semantic targets, screenshots and browser evidence while preserving user control. Skip ordinary web fact lookup.
required-tools: [browser_snapshot, browser_find]
---

Obtain the actual URL and current owned browser state. Use structure and find for accessible controls; use retained screenshots for layout, charts or canvas only when the model can read images. Exercise the requested success and important error/empty states.

Reobserve after navigation, resize or human handoff before using a target or coordinate. Inspect relevant console/network evidence without dumping unrelated sensitive traffic. A partially completed form or uncertain submission must not be blindly replayed.

Read references/targets.md for evidence conventions. Preview tools are needed only to start an authorized local server; uploading, authentication and publication need their own selected capabilities and authority. This skill never grants them.
