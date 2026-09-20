# Source provenance

Current product intent is [David's supplied thtaib vision](../../thtaib-vision.md). Revision 0.5 below is historical provenance; where its framing conflicts, the current vision takes precedence. Its archived bytes and source anchors remain for traceability.

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

## What the repository adds

Stable requirement IDs, acceptance lines, agent working instructions, the status catalogue, decision records and the checker are repository maintenance mechanisms adopted in [ADR-0004](../decisions/ADR-0004-slim-specification-pack.md); revision 0.5 did not define them. Canonical Pydantic/schema/client generation is [ADR-0002](../decisions/ADR-0002-contract-authoring.md). Details the source left open are [open questions](../open-questions.md); decisions taken since are in the [changelog](../decisions/changelog.md). Where the source is weak — frameworks named without versions, Inspect AI and llama-bench assumed to slot in, MCP Apps called experimental (now stable upstream), five execution environments listed without an isolation model, "Lab" overloaded — the repository specifications, not this archive, record the resolution. See [upstream links](upstream.md) for the original references.
