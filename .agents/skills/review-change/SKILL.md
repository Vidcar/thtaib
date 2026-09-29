---
name: review-change
description: Review a concrete diff and whether its tests prove the intended behaviour. Use independent review for consequential lifecycle, persistence, permissions, concurrency, shared-contract or verification-system changes.
---

# Review change

Read project instructions, the actual diff against its intended base, relevant callers and tests. Establish the requested outcome without relying on the implementer's conclusions. Focus scrutiny on changed boundaries and consequences, not a repository-wide audit.

Look for duplicate ownership, stale state, hidden side effects, races, permission failures and gaps in failure or recovery. Preserve distinctions between requested, saved, accepted and applied state, and between an operation and its subsequent refresh. Similar-looking operations can intentionally differ; shorter files are not proof of better architecture.

Challenge verification as well as implementation. Does the test fail for the intended violation and prove an observable result? Could a no-op callback, stale fixture, old running build or mocked dependency make the claim false-green? Scrutinize removed assertions, widened skips and reduced mandatory checks explicitly; a modified guard cannot certify its own weakening merely by passing.

Report actionable findings with location, trigger, consequence and evidence. Separate delivery blockers from optional improvements and uncertainty. No supported finding is an acceptable result; do not manufacture a quota or request stylistic churn.

When arranging independent review, give a fresh-context agent the task, base/diff and raw artifacts, not the desired verdict. Self-review is not independent review. Resolve disagreements with evidence and rerun affected checks after fixes. If agent facilities are unavailable, record that limit rather than claiming independent review. Keep review in the task or existing review channel.
