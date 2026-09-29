# Design

## Context

See proposal.md for motivation. The established app uses llama.cpp b11045 and Deep Agents 0.7.19. Workbench currently reserves half/quarter of context plus 8%, advertises the reduced remainder to the framework and overrides the framework input-budget calculation. Models has three-column resolved-value rows and multiple context controls. Memory preview invokes a slow native subprocess on ordinary edits.

## Goals / Non-Goals

Deliver the approved compact editor, native/publisher baseline and stock configured context management. Preserve existing permission, cancellation, selected-tool, checkpoint and model lifecycle guarantees. Reuse existing backend/desktop and pinned integrations; unrelated active changes and downloaded weights stay intact.

## Decisions

### Upstream context ownership

Use create_summarization_middleware(model, backend, token_counter=...) and supported name-based replacement, with one instance per agent. Pass the full observed per-request n_ctx to both adapter and harness model profiles; do not advertise a post-reservation remainder. Leave native trigger 85%, retention 10%, argument trimming, summary prompt, full-history offloading and overflow recovery untouched. Unknown capacity uses the factory fallback. Native configured positive output reservations and 5% headroom occur exactly once inside the framework.

Remove ResponseBudgetPolicy/Binding and half/quarter/8% calculations. The canonical effective native max_tokens is -1 when no deliberate finite setting exists, including cold helpers, queues and housekeeping. Existing accepted configuration snapshots still freeze exact settings. A positive output limit remains exact; the framework handles its reservation and any genuine inability to fit.

Token counting uses the native /v1/chat/completions/input_tokens endpoint with the same message/tool/schema/reasoning/media projection and template arguments as dispatch. Reuse owned clients, bounded requests and a loaded-identity/payload cache. Unavailable native counting falls back to the SDK approximation and is labelled estimated. No approximate Workbench observation independently rejects a request. Native errors are recovered or translated at the application boundary without a second compaction algorithm.

Keep request preparation/permissions in supported application middleware, ordered before the configured native counter sees the actual candidate. Housekeeping dispatch/cancellation and telemetry use public model invoke/ainvoke hooks and SDK internal-call metadata instead of private summary methods. Context observations describe full capacity, native/estimated count basis, configured output and framework activity; they do not create a second enforceable budget.

### Shared settings and defaults

The existing resolver/catalogue owns import, Models, Chat and transport facts. Add request_path to RuntimeControlDescriptor while retaining truthful flag mappings. Known resolved values are rendered directly without materialising overrides just by displaying them. Reset in contextual help clears the override and reveals its actual parent value.

New default configurations use the unambiguous compatible card preset matching native Thinking; otherwise use template/native values. Missing card fields use native values. Do not silently import a publisher output ceiling. Thinking changes preserve sampling; explicit card application changes only supplied response fields. One default configuration is sufficient; optional named setups remain user-created and shared.

Qwen initial values are temperature 1, top_p .95, top_k 20, min_p 0, presence/frequency 0, repeat 1; Thinking Xhigh; history Keep; output Unlimited; context 32768; GPU Auto/fit On; K/V f16; Flash Auto; MTP Off (draft maximum 3 when enabled). Context starts lower only when a verified model maximum is smaller. Preserve native Auto semantics rather than substitute literal zero. Use native defaults for specialist options; correct stale speculative p_min and flag aliases. Remove fit/GPU and microbatch restrictions that native code does not require and stop CPU weight placement from silently changing independent offload controls. Keep demonstrated native incompatibilities.

### Compact stable editor

At editor width >=840px, Generation/Sampling and Loading/Memory form two columns; otherwise stack. Keep Thinking/history/output plus seven numeric sampling fields and Context/GPU/K/V/Flash/MTP visible. Header contains identity, Model card, Save and load state/action. Saved configuration selector appears only with multiple setups; metadata/files/refresh/management use contextual detail.

Model card opens presets first, with card reading/link within the panel. Help contains source, reset, actual flag/request key and timing. Remove persistent explanatory prose, default/value duplicates, extra preset entry points and permanent Check settings action. Context has one slider, step 1024, exact verified maximum endpoint and readout; a display span is not an invented validation bound. Unknown ranges can expand through Advanced. Advanced retains specialist settings and optional model instructions.

Save changes future accepted response defaults; startup changes require explicit Load/Reload. Existing active/queued snapshots remain frozen. Panel overlay/docking preserves keyboard containment, Escape and focus restoration. Background metadata, estimates and validation must not remount controls or shift subsequent rows.

### Fast advisory memory

Extend the existing estimate request with method=metadata|native, default metadata. Cache local GGUF/tensor inspection by file identity; calculate known selected weights, dense attention KV, hybrid recurrent state, placement and MTP without subprocesses on slider edits. Preserve arrays/tensor names required for hybrid layouts and count shared MTP weights once. Retain partial components and distinguish unknown dynamic driver/OS/compute overhead. Optional native checking remains pinned and bounded inside Memory details. Save/Load never depend on estimate success.

## Risks / Trade-offs

- Native counting may be unavailable or expensive -> bounded requests, cache, SDK fallback and explicit counting basis.
- Approximate memory cannot prove device fit -> label estimates/unknown allocations and retain optional native check and observed runtime facts separately.
- Middleware order can distort permitted context -> verify exact selected tools/messages and native reduction before actual dispatch, including summaries and tool images.
- Removing old budget types changes saved development data -> discard authorised obsolete model overrides/budget records once; preserve weights, unrelated state and accepted live work.

## Migration Plan

Implement contracts and source together; generate wire schemas; validate deterministic/integration and real native/UI behaviour with isolated data. Reset the authorised everyday model loading/response settings through existing records/resolvers, safely reload the selected example after active work is clear and verify launcher/source/build identity. Complete the established Git/PR/merge workflow and refresh HANDOVER.md. No dependency or runtime upgrade is required.

## Setting audit

The resolver and descriptors are shared by import, installed Models and Chat. `R` means the next accepted request; `L` means explicit Load/Reload. Existing accepted and queued settings retain their exact values. Generation and Loading are immediately visible; Advanced contains specialist controls. Native defaults come from the pinned b11045 help/source, response template defaults from the verified GGUF or running `/props`, and Qwen recommendations from the [pinned publisher card](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/blob/4ca720788d1e01f1bff70c033e0d0028fd02e502/README.md). Provenance and reset are available in each control's help rather than a duplicate permanent value column.

| Setting and purpose | Initial value | Actual mapping | Evidence and retained constraints | Timing / placement |
| --- | --- | --- | --- | --- |
| Thinking: native reasoning mode/effort | Native template; Qwen On/Xhigh | `reasoning_effort`, `chat_template_kwargs.enable_thinking` | Verified template/props; reject explicit modes only when native support is demonstrated absent, not merely unknown | R / Generation |
| Thinking history: replay previous reasoning | Native template; Qwen Keep | `chat_template_kwargs.preserve_reasoning` (verified alias `preserve_thinking`) | Verified template/props; preserve active tool-cycle history even when older reasoning is dropped | R / Generation |
| Maximum output tokens: optional total thinking/answer ceiling | Unlimited (-1) | `max_tokens` | Native whole numbers >=-1, including 0; a positive explicit ceiling is reserved once by Deep Agents, publisher metadata does not impose one | R / Generation |
| Temperature: sampling randomness | Qwen 1; native .8 otherwise | `temperature` | Publisher/native; finite >=0, no invented upper bound of 2 | R / Generation |
| Top P: probability mass | Qwen .95 | `top_p` | Publisher/native; 0..1 including zero | R / Generation |
| Top K: candidate count | Qwen 20; native 40 otherwise | `top_k` | Publisher/native; nonnegative native int32, 0 disables | R / Generation |
| Min P: minimum relative probability | Qwen 0; native .05 otherwise | `min_p` | Publisher/native; 0..1 including zero | R / Generation |
| Presence penalty: discourage seen tokens | 0 | `presence_penalty` | Publisher/native; finite, the documented -2..2 guidance is not a hard engine restriction | R / Generation |
| Frequency penalty: discourage repeated tokens | 0 | `frequency_penalty` | Native default; finite, no artificial -2..2 gate | R / Generation |
| Repetition penalty: adjust repeated-token probability | 1 | `repeat_penalty` | Publisher/native; finite >=0, 0/1 disable | R / Generation |
| Context: shared token pool | 32768 or smaller verified maximum | `--ctx-size` | Native context source; one slider uses 1024 increments and the exact maximum endpoint. Native Auto explicitly omits the flag; Full uses 0. Unknown slider bounds do not impose a runtime ceiling | L / Loading; Auto/Full in Advanced |
| GPU layers: weight placement | Auto | `--n-gpu-layers` | Native 0/Auto/All/nonnegative int32; independent of fitting and companion offloads | L / Loading |
| K/V cache precision: attention cache storage | f16 / f16 | `--cache-type-k`, `--cache-type-v` | Native cache enums/block layouts; quantized V requires Flash auto/on; DeepSeek4 MLA requires matching K/V | L / Loading |
| Flash attention: native attention implementation | Auto | `--flash-attn auto/on/off` | Native help/context source; explicit value, not a bare switch | L / Loading |
| MTP: model's multi-token prediction head | Off; 3 draft tokens when enabled | `--spec-type none/draft-mtp` | Actual `nextn`/`eh_proj` GGUF tensors, not filename/family guesses; shared weights counted once | L / Loading |
| CPU generation/batch threads: CPU scheduling | Auto (-1) | `--threads`, `--threads-batch` | Native positive int32/-1; physical-core recommendation is not forced | L / Advanced |
| Batch/microbatch: native prompt processing | 2048 / 512 | `--batch-size`, `--ubatch-size` | Batch positive; native microbatch 0 and values above batch are accepted/clamped by engine rather than rejected by Workbench | L / Advanced |
| Parallel requests: simultaneous slots | Native Auto (-1) | `--parallel` | Native Auto resolves four slots and forces unified cache; explicit 0 is invalid. Runtime per-request context remains distinct from shared pool | L / Advanced |
| Unified cache: shared KV allocation | On with native Auto slots | `--kv-unified`, `--no-kv-unified` | Native server source; Auto forces On without rewriting requested arguments; divided pools require explicit parallel count | L / Advanced |
| KV / operation / projector offloading | On independently | `--kv-offload`/`--no-kv-offload`, `--op-offload`/`--no-op-offload`, `--mmproj-offload`/`--no-mmproj-offload` | Native help; CPU weight placement does not force companion changes | L / Advanced |
| Memory fitting: native placement adjustment | On | `--fit on/off` | Native help; Auto GPU layers are legal independently | L / Advanced |
| Loading mode: weight-file mapping/locking | Auto | `--load-mode auto/none/mmap/mlock/mmap+mlock/dio` | Pinned native mode names; retired standalone flag aliases removed | L / Advanced |
| Chat template: message serialization | GGUF or verified compatible publisher template | `--chat-template`, `--chat-template-file` | Explicit verified source/path, bounded template size; native compatibility retained | L / Advanced |
| Template arguments: native startup customization | None | `--chat-template-kwargs` | JSON; known response aliases are per-request fields, other keys affect startup identity | L / Advanced |
| Thinking limit/message: optional native thinking budget | Unlimited (-1) / native message | `reasoning_budget_tokens`, `reasoning_budget_message` | Native >=-1/string; native default no-op allowed on non-thinking templates, unsupported finite budgets rejected | R / Advanced |
| Thinking format: reasoning serialization | Auto | `reasoning_format` | Native auto/none/deepseek/deepseek-legacy | R / Advanced |
| Typical P: typical sampling | 1 | `typical_p` | Native probability 0..1 | R / Advanced |
| Seed: deterministic randomness | Random (-1) | `seed` | Native -1 or uint32 | R / Advanced |
| Logit bias / stop: specialist token controls | None | `logit_bias`, `stop` | Native finite biases/false/list/object and supported stops; compatible explicit guidance only | R / Advanced |
| Speculation type / separate draft model | None | `--spec-type`, `--spec-draft-model` | Pinned native enums/artifacts; explicit existing draft path, no full-file hashing during metadata preview | L / Advanced |
| Draft maximum/minimum tokens | 3 / 0 | `--spec-draft-n-max`, `--spec-draft-n-min` | Native nonnegative int32; engine owns min/max clamping, no invented coupled gate | L / Advanced |
| Draft acceptance/split probabilities | 0 / .1 | `--spec-draft-p-min`, `--spec-draft-p-split` | Pinned common.h defaults and 0..1; obsolete .75 default removed | L / Advanced |
| Draft CPU/batch threads | Auto (-1) | `--spec-draft-threads`, `--spec-draft-threads-batch` | Native scheduling domains; independent controls | L / Advanced |
| Draft GPU layers / K/V precision | Auto / f16 / f16 | `--spec-draft-ngl`, `--spec-draft-type-k`, `--spec-draft-type-v` | Native cache/placement domains and matching artifacts | L / Advanced |
| Optional model instructions | None | Application `system_prompt` instruction layer | Application responsibility; no invented native CLI flag | R / Advanced |
| Embedding / pooling | Off in Chat; native/GGUF pooling in embedding flow | `--embedding`, `--pooling mean/cls/last` | Native embedding-only flow; specialized token/rerank flows remain separate | L / Embedding flow |
| Default versus Chat purpose | Removed | No distinct native behavior | A duplicate application label is not a configuration setting | Removed |
| Memory preview / allocation check | Metadata; native check only on demand | Existing estimate API `method: metadata/native` | Advisory partial components; unknown overhead is not zero or verified fit and errors cannot block Save/Load | Edit / Loading details |
| Host/port/alias | Managed loopback/assigned identity | `--host`, `--port`, `--alias` | Application process/router ownership; an optional fixed port is validated before launch, while host and alias remain managed | Managed lifecycle; fixed port in Advanced |

Native evidence: [arg.cpp](https://github.com/ggml-org/llama.cpp/blob/b11045/common/arg.cpp), [common.h](https://github.com/ggml-org/llama.cpp/blob/b11045/common/common.h), [context allocation/validation](https://github.com/ggml-org/llama.cpp/blob/b11045/src/llama-context.cpp), [automatic slots/unified cache](https://github.com/ggml-org/llama.cpp/blob/b11045/tools/server/server.cpp), [speculation](https://github.com/ggml-org/llama.cpp/blob/b11045/common/speculative.cpp), [native counting endpoint](https://github.com/ggml-org/llama.cpp/blob/b11045/tools/server/README.md).

## Framework customization audit

The [installed Deep Agents 0.7.19 factory](https://github.com/langchain-ai/deepagents/blob/deepagents%3D%3D0.7.19/libs/deepagents/deepagents/middleware/summarization.py) owns summarization trigger/retention, its 5% input headroom, explicit positive output reservations, summary prompt, argument trimming, history offloading and overflow retries. Workbench supplies one replacement named `SummarizationMiddleware`, the full observed model profile, the existing backend instance and a configured `token_counter`. It does not override private summary generation or `_input_budget`.

| Retained extension | Application responsibility | Supported integration |
| --- | --- | --- |
| Native token projection/count cache | Local llama.cpp template, reasoning and media representation | SDK `token_counter` option; bounded existing HTTP clients |
| Summary dispatch decorator | Cancellation, model-use scope and housekeeping request attribution | Public model `invoke`/`ainvoke`, SDK internal-call metadata passed unchanged |
| Request preparation before summary | Selected tools, permissions and stable application outline | Public Filesystem middleware replacement/preparation hook; native filesystem and trimming remain intact |
| Final request projection | Actual selected media/browser observations, canonical reasoning replay | Adapter request hook, with observational counts and genuine native overflow recovery |
| Execution / persistence / visibility | App lifecycle, accepted configuration, permissions, cancellation, checkpoints and UI | Existing LangGraph/Deep Agents config, middleware and adapter boundaries |

## Metadata preview validation

The real Qwen GGUF has 866 readable tensors. Metadata preview measured 442 ms cold and 12.34 ms warm median; successive Context edits at 33792, 65536 and 98304 took about 13 ms. At 32768 without MTP it retains 13,890,840,576 weight bytes, 2,147,483,648 attention-cache bytes and 627,572,736 recurrent-state bytes. MTP adds its unshared head weights once and native rollback state; projector bytes remain separate. Dynamic compute/driver/host-cache allocations remain explicitly unknown. These figures are estimates, not a verified device fit. Focused tests cover partial unknowns, dense/hybrid layouts, tensor cache invalidation, MTP/separate drafts, slot pools, failed native helpers and unavailable hardware.

## Native context validation

The restored Qwen loaded with 32768 context, native automatic GPU layers/fitting, Flash Auto, unified cache and four automatic slots. Native properties report the full 32768 per request. Thinking On and Off requests both sent max_tokens=-1 and kept the stock compaction threshold at 27852. The framework input budget was 31129 with Unlimited output and 30129 with an explicit 1000-token ceiling, demonstrating one reservation.

A real 29255-token history triggered one stock summary and completed the answer. Native summary and final request counts matched llama.cpp usage at 27454 and 2833. Partial assistant-only histories that the Qwen template rejects fall back for that count without disabling later successful native counts.

With the counting endpoint deliberately unavailable, a synthetic Unicode history measured 35802 natively but 16091 approximately. The unchanged Unlimited request produced a real exceed_context_size_error, then the SDK recovered through one successful summary and a successful answer. Summary input/output was 30482/284 and final input/output 6389/6. Every request retained max_tokens=-1; canonical history and its complete tool/result pair remained unchanged. Isolated captures live under .scratch and contain no product-state migration.

Native MTP generation drafted 75 tokens and accepted 66, with the default draft maximum of three and the full 32768 capacity. The actual slots reported speculation enabled. The pinned server's `/props` task-default serialization copies sampling into a fresh task object but omits speculation; its reported `none` is not evidence that MTP is inactive. Exact native input count matched usage at 89 tokens. MTP was then reset to Off for the delivered stock configuration.
