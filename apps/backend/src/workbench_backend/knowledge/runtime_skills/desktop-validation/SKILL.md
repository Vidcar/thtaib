---
name: desktop-validation
description: Test an authorized Windows application with accessibility targets and retained screenshots while preserving its live window scope. Use for native/Electron work that requires desktop inspection.
required-tools: [desktop_inspect, desktop_search]
---

Read the current Selected/All window grant and current window identity. Use shallow inspection or targeted search before invoking a control. Prefer selected set_value and invoke operations to long keyboard sequences.

Capture visual evidence only when needed and image reading is available. Recheck after focus, process or target changes. A recycled handle, closed window, revoked scope or blocked key must stop the relevant action; never choose a wider window grant from this skill.

Read references/windows.md for identity and uncertain-effect rules. Shell is not a universal prerequisite and a saved setup cannot manufacture a live window grant.
