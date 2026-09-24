# Tasks

## 1. Discovery and provenance

- [x] 1.1 Discover bounded GGUF candidates for source-only links and verify conversion lineage against pinned source revisions; test matching, mismatching, inaccessible and ambiguous repositories.
- [x] 1.2 Download and hash exact publisher configuration files into an isolated bundle namespace and persist their provenance; test collision, hash failure and restart behavior.

## 2. Applied configuration

- [x] 2.1 Parse and record selected template, generation defaults, unsupported fields and GGUF metadata comparisons; test both compatible and conflicting examples.
- [x] 2.2 Validate an explicit publisher-template choice against the managed runtime, use the chosen template at launch, and expose loaded versus selected state; test failure without silent fallback.
- [x] 2.3 Merge verified generation defaults below explicit settings in shared backend resolution and send them over the real adapter, including verified token suppression; test wire values and persistence.

## 3. Desktop and contract

- [x] 3.1 Show source-to-GGUF choices, pinned sources, selected template, applied defaults and unsupported reasons in the desktop; verify the desktop build and shared API contract.
- [x] 3.2 Validate this change's Models spec and update the established handover with checked state; run OpenSpec strict validation.

## 4. End-to-end delivery

- [x] 4.1 Run backend default and integration suites plus the desktop build and contract check; resolve failures.
- [x] 4.2 Through the desktop, freshly download Qwen3.8-27B Q4_K_M and Gemma 4 12B Q4_0 from source links, launch both, inspect rendered prompts and transmitted settings, chat, and repeat after restart; verify publisher-template selection on at least one.
- [x] 4.3 Deliver the validated change through the repository Git workflow and report exact checks and any unverified behavior.
