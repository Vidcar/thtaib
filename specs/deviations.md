# Known deviations from the intended design

The application repository has been inspected through Issues #1, #3, #12, #15 and #17 (Issue #23 audit). Implementation gaps are recorded as `planned` / `partial` catalogue rows and [open questions](open-questions.md), not as deviations, unless running code is known to contradict intended design.

There are **no recorded deviations** at this audit. Issue #27 moved run/chat linkage into `application.sqlite` with a separate `checkpoints.sqlite`. Remaining JSON stores (model-manager bundles/profiles/deployments, Lab cases, knowledge versions) belong to those modules and are not an approved waiver of [STATE-001](modules/state-recovery.md#state-001). Identities, event reconciliation, exactly-once and external-effect remainder stay [OQ-004](open-questions.md#oq-004). That is not a claim that the implementation conforms.

Use this file for observed divergence. Use [open questions](open-questions.md) for unresolved design, not for known bugs hidden as questions. Keep the affected requirements' actual implementation status in [the catalogue](catalog.json).

## Entry format

For each new entry, assign an unused `DEV-NNN` identifier and record:

```text
Identifier and concise title:
Affected requirement IDs:
Observed behaviour and inspected revision:
Intended behaviour (link, do not duplicate the requirement):
Risk and affected users/data/environments:
Owner:
Disposition: fix / propose design change / approved temporary deviation
Approval reference (required for a temporary deviation):
Scope and compensating controls:
Review or expiry trigger (a date, release or explicit milestone):
Reproduction and tracking reference:
Resolution evidence and date:
```

Temporary approval does not mark the requirement verified. Keep its status `partial` until full compliance is evidenced or the requirement is formally changed. Do not silently extend an expired deviation, remove its test, or rewrite the specification to match it. Record closure with its evidence and retain the entry for history.
