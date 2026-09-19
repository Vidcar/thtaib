# Feature: REPLACE_WITH_FEATURE_NAME

Fill this in before implementing. Keep it in the pull request (or link it from the issue); it is a working record, not a specification. When the work lands, the durable parts move into the module specification, the catalogue and the changelog.

## Outcome

One paragraph: what David can do afterwards that he cannot do now, in plain English. Explicitly out of scope:

## Requirements touched

| ID | Current status | Expected status after | Specification change (or "unchanged, because …") |
| --- | --- | --- | --- |
| REPLACE_WITH_ID | planned / built / verified | | |

New requirement IDs, if any, with their proposed anchor and acceptance line:

## Upstream research

For every llama.cpp, LangChain, LangGraph, Deep Agents or other dependency behaviour this relies on: the pinned version, the documentation or source consulted (URL or file), what it supports, what it does not, and what the framework already provides that the application must not reimplement.

| Dependency and version | Source consulted | Finding |
| --- | --- | --- |
| | | |

Assumptions, unknowns and dependencies that remain:

## Interfaces

Routes, records, shared-contract changes, events, settings keys, file layouts. Name the owning module for each. State what is module-local and what must go through generated contracts.

## Behaviour

Intended behaviour including the failure paths: cancellation, restart, unavailable runtime, denied permission, unknown effect. Say what the user sees in each case.

## Acceptance checks

Observable checks a reviewer can repeat, one per line. Each maps to a requirement's acceptance line or extends it.

## Validation plan

| Level | What it proves | Command or procedure | Environment |
| --- | --- | --- | --- |
| Unit | code paths, against fakes | | CI |
| Real-model CI smoke | plumbing against a tiny GGUF on CPU llama-server | | CI |
| David-PC UAT | managed inference and capability with the preferred capability UAT model | | David-PC |

State which rows are not applicable and why. A capability claim without the UAT row stays `built`.

## Reconciliation list

Files to update in the same pull request: module specification sections; catalogue rows (status, code, tests, evidence); repository-map bindings; commands; decisions changelog entry; deviations opened or closed; glossary terms; open questions narrowed or resolved.

## Handoff (if unfinished)

Branch and commit; what is done; what is not; next concrete step; reproduction commands; open decisions and who owns them.
