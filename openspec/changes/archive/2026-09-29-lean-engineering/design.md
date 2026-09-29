# Design

## Context

The clean main checkout at `ada3476` has generated OpenSpec skills, a tiered Python unittest runner, and a desktop build containing component/browser regressions. Installed Codex CLI is `0.158.0-alpha.2.1`; official documentation and the installed skill catalog support root `.agents/skills` discovery from subdirectories. See proposal for motivation.

Source guidance: [local skill discovery](https://learn.chatgpt.com/docs/build-skills), [AGENTS discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [lean instructions](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) and [behavioural skill exercises](https://developers.openai.com/blog/eval-skills). Installed CLI help governs invocation flags.

## Goals / Non-Goals

Make scoped local evidence and independent review routine. Do not create an enforcement service, automatic refactoring schedule, second test framework or application stabilisation claim.

## Decisions

- Four short skills use local project instructions to find owners, contracts and checks. Keep project commands in AGENTS and the verification script; preserve generated OpenSpec skills.
- Python entry point under `scripts/` uses existing runtimes and subprocess commands. Explicit additive scopes default conservatively to all areas; shared scope includes both consumers. Fast permits focused tests, acceptance runs required area gates, delivery adds explicitly requested runtime checks and leaves live claims to observed evidence. Do not infer adequate scope solely from filenames.
- Record command outcomes, revision and working-tree fingerprint under `.scratch/`. Mark failures, unavailable checks and changed inputs honestly; automatic results do not certify independent review or a running app.
- Use existing unittest/component test helpers, including failing disposable fixtures. Keep a small repeatable skill exercise resource; inspect fresh Codex traces rather than treating metadata validation as behaviour proof.
- No hook: documented invocation avoids repeated full suites and needs no global settings. Trusted local checks are not a security boundary.

## Risks / Trade-offs

Explicit scopes need engineering judgment; default all and skill-guided impact analysis reduce accidental omissions. Generated skills contain generic planning pauses; explicit user authorization controls this end-to-end delivery without editing generated files. A running desktop can lag a successful build; this task will only refresh it if needed to substantiate the pilot.
