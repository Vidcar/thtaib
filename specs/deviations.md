# Known deviations from the intended design

No application repository has been assessed while preparing this pack. There are **no recorded deviations yet**, which is not a claim that the implementation conforms.

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
