# Source provenance

## Original supplied document

[Local AI Workbench Starter Specification — revision 0.5](Local_AI_Workbench_Starter_Specification_Revision_0_5.docx), dated **18 September 2026**, supplied by the user. The document title also uses “The House: That AI Built”. The archived bytes are unchanged.

SHA-256:

```text
439658bb38e89a3962543b9058594c25d4730e78667f9993b7b9fd98ac745ff8
```

The checker validates this archive against the digest stored in [the catalogue](../catalog.json). Do not replace its bytes with an edited document while retaining the same source identity. Add a separate source/version and a reviewed change when new source material is supplied.

This archive is provenance, not a second living specification after adoption. The following references identify source locations; they do not claim the source's requested behaviours are already supplied by dependencies.

<a id="experience-boundaries"></a>
## Experience boundaries — pages 1–2

Windows-first local workbench; guided but non-restrictive controls; optional evaluation; inspectable evidence/context; shared durable project state; versioned knowledge; optional budgets unset by default; autonomy separated from access; understandable environment choices and extensibility. The architecture pack preserves the implications for framework and ownership, not a UI design specification.

<a id="technical-components"></a>
## Technical components — page 3

The source's component/ownership table: model weights/tokeniser/template, inference/runtime/server, application model management, Deep Agents/LangChain/LangGraph, context and durable knowledge, tools/MCP, environments, retrieval, persistence, evaluation, backend, desktop and extensions. The shared rule is upstream capability plus application-owned configuration/lifecycle/visibility/contracts.

<a id="models-and-inference"></a>
## Models and inference — page 4, section 1

Hugging Face/huggingface_hub, llama.cpp/llama-server, gguf-py, application model management; bundle/profile/deployment/compatibility/run records; revision-pinned downloads; provenance; requested versus applied settings; and the narrow LangChain model-adapter handoff.

<a id="agents-and-workflows"></a>
## Agents and workflows — page 5, section 2

Harness and graph ownership; named subgraphs and child subagents; actual request capture; durable knowledge policy; completion evidence; optional task budgets versus real limits; safe continuation; programmatic tool calling and tool discovery/selection. The source classifies rubric and interpreter integration as beta.

<a id="application-infrastructure"></a>
## Application infrastructure — page 6, section 3

Modular Python/FastAPI backend; Pydantic/JSON Schema; Electron/React/TypeScript/React Flow; separate SQLite application/checkpoint stores and files; MCP integration; ComfyUI; llama-bench/Inspect AI; environments/Compose; state/snapshots/branching; run-to-Lab capture; and MCP Apps host responsibilities.

<a id="integration-registry"></a>
## Versioned integration registry — page 7, section 4

Definition identity/version, connections, configuration, capability/policy, execution/state, evidence and presentation; separate configuration/workflow links; backend validation; unverified capability visibility; common run hierarchy and approvals without bypass.

<a id="build-order"></a>
## Build order and implementation checks — page 7, section 5

First managed inference, then complete real agent work, then reuse/experimentation, then optional extensions. Long-run acceptance requires continuation beyond upstream defaults without hidden quotas, duplicated actions or lost state, and explicit stop reasons.

## What this pack adds

Stable requirement IDs, acceptance examples, agent working instructions, status/traceability metadata, change review, documentation checks and repository-protection instructions are **proposed maintenance mechanisms**, not claims that revision 0.5 already defined them. Canonical Pydantic/schema/client generation is a separate [proposed decision](../decisions/ADR-0002-contract-authoring.md).

Open questions expose details absent from the source. Security, lifecycle and consistency cautions in the module prose identify matters requiring a decision before unsafe assumptions; they do not claim a complete security design was supplied. See [upstream links](upstream.md) for original references and the small set of additional official maintenance references.
