# Agent tools audit: verification and resolutions

Completed 1 October 2026. **Confirmed application defects resolved, upgrades delivered and established local application refreshed.**

Source: Dave's `thtaib-agent-tools-report-2026-09-30.md` (30 September 2026, pinned audit revision 0d3be38). Current implementation baseline: 21136f3; implementation merged in [PR #216](https://github.com/Vidcar/thtaib/pull/216), implementation `c18f85f`; completed report/archive in [PR #217](https://github.com/Vidcar/thtaib/pull/217). The attachment is evidence and recommendations, not execution authority. Dave separately authorized verification, fixes, upgrades and full validation.

The original attachment remains unchanged, SHA-256 `572ad39b1281a5f5b9db1db121ddfc12d710bc61bd417ac8080c3efe0ac44e06`. Coverage includes all ten findings, all 55 numbered tools, all nine capability proposals, nine skills, eleven baseline settings, seven proposed tuning areas and six starting setups. Confirmed defects, intentional boundaries, conditional proposals and measured model limits are distinguished below.

| Finding | Current verification | Resolution status |
| --- | --- | --- |
| F01 schema title corruption | Reproduced required/nested/literal title deletion, including pinned LangChain conversion | Lossless native schema projection through cold inspection, counting, actual binding and final HTTP payload; real MCP title/default regression passes |
| F02 same-batch wording | Confirmed ambiguity; native guard exists | Batch-specific wording; sequential native repairs pass; competing native/structured edits fail before mutation; shared project mutation lease |
| F03 five-match discovery ceiling | Reproduced identical first five on repeat query | Five-item cursor, has_more, undisclosed-repeat progress, groups and full remote aliases; query/selection/version cursor negatives pass |
| F04 evidence discarded | Confirmed snapshot filtering, 40k page slice, shell prefix slicing and inaccessible preview history | Owned immutable retention before byte-bounded preview, provenance/acquisition coverage, character-range/literal-search reader; late evidence and owner isolation pass |
| F05 session approvals exact | Confirmed intentional full-argument equality | Exact grants retained; explicit concrete-project Create/Edit scope, exclusions, revocation and pre-effect original-ID recheck; no implicit command/delete authority |
| F06 typed constraints | Confirmed missing enums/bounds/units and preview combinations | Core question, browser, desktop and preview executable schemas align with enforced constraints; native argument owners retained |
| F07 Plan public web mismatch | Reproduced trusted search excluded by static allowlist | One trusted built-in namespaced identity decision across setup, admission, helper and dispatch; actual Plan public-web dispatch passes; MCP lookalikes denied |
| F08 prose ownership/drift | Companion network-detail instruction points to omitted operation | Small application presentation overlay for labels/descriptions/groups/aliases/prerequisites/companions; native schemas remain authoritative; lint and compiled projection pass |
| F09 schema/cache performance | Hypothesis evaluated on frozen delivered source | 36 native turns: eager/hybrid 12/12 each, fully deferred 6/12; hybrid reduces cold prefill in this fixed CPU fixture. No universal cache/loading-policy change; measured limits below |
| F10 virtual skill paths | Confirmed intentional virtual/host distinction | Nine opt-in native Knowledge packages plus explicit frozen-version/hash Python-script bridge; actual Windows execution and failed-exit evidence pass |

## Additional capability upgrades

| Upgrade | Work |
| --- | --- |
| Network request details | Implemented pinned browser_network_request; real Chrome HTTP 500 body beyond 45k read with query/cookie/password redaction |
| Page/log continuation | Implemented read_tool_result in existing owner route; exact characters or bounded literal matches, identity/hash/acquisition coverage; symlink/junction/host paths denied |
| Native deletion | Explicitly selected native delete; protected-root/framework/link and entire-subtree preflight; exact Ask gate; compiled native deletion/Plan/default tests pass |
| Structured edits | apply_edits validates all exact edits against original bytes, optional read-only preview, SHA-256 apply and atomic replacement; stale/overlap/unmatched bytes unchanged; native/custom mutation lease shared; 20 paired native/atomic comparisons confirm atomic-failure benefit without a speed claim |
| Media emulation | Implemented pinned browser_emulate_media; dark/reduced-motion and clear confirmed in live Chrome |
| Managed commands | start_command/command_status/stop_command use existing owned process/effect infrastructure; actual Windows timeout/cancel/detached-child/restart tests; run/helper finalization stops jobs, failures stay uncertain |
| MCP resources | list_connection_resources/read_connection_resource through pinned FastMCP client; frozen ID/name/version visible in native model schemas, page/byte limits and retained text; actual native binary, exact/exceeded UTF-8 limit, correctable input recovery and post-read revocation tests pass |
| Semantic navigation | Evaluated the existing selected MCP integration boundary; no repository-shipped/tested semantic integration or measured task need found. Original recommendation is conditional/later; no invented tool, connection or competing index added |
| Skill scripts | execute_skill_script validates selected accepted version and manifest before materializing package into owned execution scope; independently selected execute and Work project required; literal arguments, real failed exit and tamper/deselection tests pass |
| Runtime skills S01–S09 | Nine explicit-install, native versioned instruction/reference packages; reinstall preserves edits; conditional bodies/references and frozen/off mechanisms tested; 18 conditional model probes recorded; limitations below |
| Setup guidance | Six starting templates populate reviewable New agent drafts with real installed IDs; Chat access/mode/window grants remain explicit; no automatic save/enable/model retune |

## Every original tool recommendation

The rows below record the disposition of all 55 numbered recommendations. Tests verify shared boundaries as well as the individual changed tools; inherited behavior is retained where the audit proposed clarification rather than a replacement.

| # | Tool | Resolution |
| --- | --- | --- |
| 01 | echo | Explicit diagnostic choice; omitted ordinary defaults and templates |
| 02 | time_now | UTC ISO-8601 stated accurately |
| 03 | ls | Immediate project listing versus virtual Knowledge/result routes clarified |
| 04 | read_file | Native zero-based text lines, pagination and image/capture reading retained and documented |
| 05 | write_file | Create/overwrite, read-before-replace and same-batch semantics clarified; native owner retained |
| 06 | edit_file | Exact unique/current source, native newline/error semantics retained; later repair allowed |
| 07 | glob | Pinned basename-any-depth and leading-root anchoring described; hidden-directory semantics preserved |
| 08 | grep | Literal search and native output modes/bounds exposed; no silent regex change |
| 09 | execute | Real host/cwd/environment authority explicit; UTF-8 byte preview, full bounded acquisition/tail and exit/process evidence retained |
| 10 | write_todos | Progress-driven changed checklist; duplicate unchanged same-batch calls discouraged |
| 11 | ask_user | Shared typed enum/bounds/choice validation; path answers grant no new access |
| 12 | propose_memory | Narrow proposal guidance; identical pending destination/content/base reused only after validation; accepted/rejected/stale proposals never silently reused |
| 13 | read_attachment | One-based document/page versus section line and zero-based character semantics; literal query/provenance preserved |
| 14 | find_tools | Complete paged/grouped/alias discovery, stable query/selection-bound continuation and exact rediscovery |
| 15 | read_reference | Frozen version/hash checked character pages, exact source/coverage/next_read; short resources returned whole |
| 16 | search_knowledge | Bounded 600-character hit excerpt with retained full chunk and coordinates; lexical AND/no-embedder/error semantics unchanged |
| 17 | task | Explicit eligible helper, self-contained relevant brief, parent scope and no nested generic delegation |
| 18 | browser_navigate | Current page/session/revision and retained full snapshot before preview; readiness remains observed |
| 19 | browser_navigate_back | Fresh active-page and state evidence; history/side-effect limitations clear |
| 20 | browser_tabs | Typed list/select/close/create semantics and required index; listing does not request action approval |
| 21 | browser_snapshot | Full permitted text retained; structural excerpt not treated as complete page evidence |
| 22 | browser_find | Pinned text/pattern/limit semantics retained; current semantic control targets distinct from page reading |
| 23 | browser_click | Fresh targets and owned approval; stale worker epoch rejects mutations; unknown outcomes not replayed |
| 24 | browser_hover | Effect/current-target guidance and fresh page observations |
| 25 | browser_press_key | Pinned key semantics and focus/current-page guidance |
| 26 | browser_type | Ordinary fill versus typing/submit effects explicit; credential handling retained |
| 27 | browser_select_option | Native selection choices preserved; field effects/current target made explicit |
| 28 | browser_fill_form | Non-atomic earlier-field effects explicit; acknowledged failures retain partial-effect/inspect/no-replay guidance; native first-field effect, second-field failure and single-dispatch proof pass |
| 29 | browser_resize | Typed enforced pixel bounds; current viewport observation invalidates earlier coordinates |
| 30 | browser_console_messages | Bounded redacted diagnostics retained before preview, level/limit semantics preserved |
| 31 | browser_network_requests | Safe retained request summaries and available native request-detail companion |
| 32 | browser_take_screenshot | Existing retained image/capability path preserved; charts/canvas and viewport/full-page coordinate caveats clear |
| 33 | browser_wait_for | Seconds bounded 0–30 in schema/runtime; observed text/readiness instead of arbitrary sleep guidance |
| 34 | browser_handle_dialog | Accept/dismiss side effects, active dialog/current page, approval and unknown effect distinctions |
| 35 | browser_drag | Native semantic gesture retained with fresh source/destination guidance |
| 36 | browser_mouse_move_xy | Current viewport coordinates require fresh viewport screenshot evidence |
| 37 | browser_mouse_click_xy | Fresh screenshot epoch/geometry plus click approval; stale navigation/handoff/resize denied |
| 38 | browser_mouse_drag_xy | Current viewport path and gesture/cleanup guidance, semantic drag preferred |
| 39 | browser_mouse_down | Explicit persistent pointer state; lifecycle cleanup remains owned |
| 40 | browser_mouse_up | Explicit pointer release/current state; same owned action boundary |
| 41 | browser_mouse_wheel | Typed delta/units and current viewport guidance |
| 42 | browser_file_upload | Selected project files plus chooser and action authority; no manufactured host path/file grant |
| 43 | start_preview | Mutually exclusive typed modes, per-operation timeout, launch identity and HTTP-only readiness proof |
| 44 | stop_preview | Exact owned preview/process-tree lifecycle retained; stop uncertainty not converted to success |
| 45 | preview_status | Full bounded current-launch logs/read continuation and archived previous launches; late failures retained |
| 46 | desktop_list_windows | Filter/pagination only inside granted live window scope |
| 47 | desktop_inspect | Bounded tree/depth/control limits and native selector units; large allowed evidence retained |
| 48 | desktop_search | Pinned selector grammar/match limits; live identity/selected-window enforcement |
| 49 | desktop_wait | Bounded timeout/interval and exact WinApp property syntax; installed WinApp 0.7 worker passed live Unicode property wait and selected-window/revocation checks |
| 50 | desktop_invoke | Existing live HWND/PID grant and stale/revoked identity denial; effect/uncertainty guidance |
| 51 | desktop_set_value | Semantic native value operation, live selected target and bounded input |
| 52 | desktop_send_keys | WinApp key grammar, focus/global-input constraints and real capability requirements |
| 53 | desktop_screenshot | Retained capture, fresh process/window identity and image-coordinate metadata preserved |
| 54 | search_web | Selected canonical namespaced built-in trusted public search allowed in Plan; normal empty results preserved |
| 55 | read_web_page | Full allowed extracted text retained before preview, source URL/coverage/continuation and 2MB acquisition bound; DNS/redirect protections unchanged |

External MCP operations continue through the official adapter with frozen namespace/schema/version/session identity and exact approval. Discovery uses human connection names and full remote aliases. An arbitrary MCP annotation, resource or document cannot promote itself to trusted Plan or grant another capability.

## Runtime skills and settings

S01 project-change, S02 failure-diagnosis, S03 windows-execution, S04 verify-delivery, S05 browser-validation, S06 desktop-validation, S07 evidence-research, S08 delegate-review and S09 memory-curation are shipped as explicit-install Knowledge skill packages. Each has discriminative metadata, a compact conditional body and one inert conditional reference. Installation is idempotent, preserves user-edited versions and selects nothing in existing conversations. Repository development skills are separate.

Settings → Permissions can grant Create/Edit for one registered project, with `.git` and user exclusions and explicit duration/revocation. Existing exact grants remain exact. Knowledge → Skills offers the bundled pack. Agents → New agent → Starting template offers guarded builder, trusted builder, read-only reviewer, browser validator, evidence researcher and Windows validator. Templates only fill a draft; no IDs, saved authority or external connections are fabricated.

Deferred loading and a small task-specific pinned set remain the starting default. Pins do not grant capabilities. Chat owns Work/Plan, Ask/Full access and live Windows grants; templates state these prerequisites visibly. Model/context/sampling settings inherit the existing working setup. Review defaults off; memory, connections, helpers and embedding remain deliberate selections. Whole-task budgets remain optional and separate from operation acquisition/timeout limits. The measured F09 result supports task-specific pins for this fixture; no universal loading or cache-reset policy is inferred.

| Original settings recommendation | Delivered disposition |
| --- | --- |
| Tool loading | Existing `when_needed`/`always` retained; fixed-source comparison below |
| Pins | Task-specific real-ID pins retained; pin selection grants no new authority |
| Work/Plan | Implementation uses Work; reviewers/research can use Plan with the now-correct trusted public-web eligibility |
| Ask/Full access | Reviewable Chat choice retained; scoped Create/Edit is an additional explicit grant, not a shell sandbox |
| Desktop access | Off unless needed; selected Windows template states the independently required live window grant |
| Inherit deployment settings | Templates preserve the working model draft and inherited settings; no universal context/thinking/sampling/output values applied |
| Automatic review | General baseline remains off; consequential review stays explicitly selected |
| Memory/skill references | Nine optional installable packages; applicable frozen references are selected deliberately; explicit empty selection retains its meaning |
| Embedder | No guessed embedder; lexical knowledge search remains usable independently |
| Helpers | No automatic helper; independently selected narrow helper access/version/context preserved |
| Total task budgets | Optional and separate from operation limits; evaluation bounds are not saved product policy |

The seven proposed tuning areas are resolved as follows; these are mechanisms and guidance, not invented setup keys.

| Proposed control | Delivered disposition |
| --- | --- |
| Search batch | Five initial matches, reliable cursor/repeat continuation and exact lookup |
| Page/log preview | Owner-specific bounded serialized UTF-8 previews, full permitted acquisition retained first and authorized continuation; no universal unmeasured character target |
| Screenshots | Viewport/element interaction guidance, selective full-page review, retained capture geometry and image-capability checks |
| Mutation scheduling | Shared project lease and existing browser/window effect owners serialize dependent effects; eligible independent reads retain upstream scheduling |
| File permissions | Explicit registered-project Create/Edit grant with exclusions/revocation; exact grants retained without migration; read authority stays separately owned |
| Discovery retention | New-turn reset retained; measured cache/discovery evidence does not justify broader stale disclosure retention |
| Long jobs | Owned identity/status/stop/output and truthful timeout/cancellation/cleanup; total task budget remains optional |

## Verification and actual evidence

Final backend delivery passed on frozen inputs: **1,410 default tests (one declared skip), 222 integration tests (three declared skips), and all four required real-model smoke tests**. No mandatory gate was bypassed. Report: `.scratch/verification/20261001T010138Z-a93fa98f/report.json`, input fingerprint `3195478bedb190e50fd62965242d2f92984d2b9a0c308e2990fc91de9e611e50`. The unchanged desktop build and generated-contract freshness passed in `.scratch/verification/20261001T002600Z-1945e98e/report.json`; that earlier combined report remains incomplete because its old smoke failed. Those failures were corrected and the entire affected backend delivery rerun passed. Synced specs/whitespace passed `.scratch/verification/20261001T010122Z-5f57f4c9/report.json`. Only two terminal blank lines in new tests were removed after that run. Independent byte-for-byte reconstruction reproduces the passed 104-file snapshot; no semantics changed. Both staged/working whitespace and specs then passed `.scratch/verification/20261001T011312Z-31cb4ebd/report.json`. Later report/checklist updates do not change application inputs.

Fresh-context independent review cleared permission, persistence, lifecycle, projection and validation changes. The final 104-file source/test/contract/spec fingerprint is `7d2bf9d7817e2cdeb7e7f84105d47581cae28f36279ddc48c6cbad24de6c29dd`. Review and reproducible reader: `.scratch/audit/independent-review.md`, `review-fingerprint.py`. All 101 previous requirements and 302 scenario names survive; seven requirements are added and two changed, with exact delta/main parity. Mandatory desktop guards remain intact; no remote CI was added.

Final archive documentation/specification and staged/working whitespace acceptance passed `.scratch/verification/20261001T015652Z-ef59dedf/report.json`. Independent post-archive logical verification reproduces the same 104-file fingerprint: 101 files unchanged, only the three identical delta specs moved to the dated archive. Evidence: `.scratch/audit/independent-reviewed-logical-manifest.json` and `review-logical-fingerprint.py`. The final documentation commits add no application, test, build or main-contract changes.

Actual production Electron UAT passed Create-only project grants/exclusions, persistence/revocation across renderer reload, explicit bundled-skill installation without added authority, template model-draft preservation and saved agent/skill reopening. Nine screenshots, production artifact hashes and process identities are recorded under `.scratch/lab-workbench/agent-tools-native-20261001-010252/`. Native Chrome 154 / Playwright MCP 0.0.82 passed long-page/request evidence, credential redaction, media changes, partial form failure and fresh handoff targets. WinApp 0.7.0 passed selected-window identity, Unicode property wait, invoke/crop, revocation and owned cleanup. These tests used isolated data and owned workers.

Review and native probes found additional confirmed defects: repeated-cancellation project-lease cleanup, retaining model drafts through template Back/apply, before/after partial-deletion evidence, native custom-tool type/extras, correctable reference ranges, frozen resource identity schema and typed Windows admission. Each was corrected with affected negative/positive regressions. The required smoke also exposed a genuine continuation guard defect: canonical SDK text and mirrored tool-call blocks were rejected by a string-only template flag although the native endpoint accepts them. The corrected guard changes no checkpoints, admits only representable text/matching call duplicates, and still rejects unknown/audio/image/malformed/conflicting blocks and incomplete pairs. Actual write, same-thread native history, wire settings/readiness and projectless authority now pass.

Actual compiled browser completion/cancellation and deferred stdio MCP controls passed. The browser generator-close noise came from scratch evaluation teardown closing its owner loop first; the fixture now follows the already-correct production shutdown order. No unsupported application lifecycle patch was added. All evidence paths here are repository-root-relative development artifacts; they contain separate source/state fingerprints and are deliberately excluded from Git.

## Original twelve acceptance exercises

| Exercise | Completed evidence | Practical boundary |
| --- | --- | --- |
| Title-bearing MCP schema | Real pinned local MCP, native ToolNode and actual wire projection preserve title/default/nested schema; conforming scripted and GGUF calls pass | Local protocol fixture; no private integration audit |
| Find the sixth relevant tool | Native discovery reaches all twelve matches by cursor/repeat, exact lookup and changed-selection denial; GGUF follows returned cursor and finds sixth tool | Original 224-token probe safely fails an incomplete call; separate 768-token functional follow-up passes, excluded from comparative timings |
| Read–edit–test–edit | Actual native filesystem and compiled scripted graph allow later repairs and reject competing same-batch writers | Intermediate file assertions; not a GGUF-selected test workflow |
| Long command output | Actual Windows processes retain late Unicode/error/exit evidence and clean owned children; GGUF uses retained-result search for buried value and correct exit0 | Model citation span inaccurate; portable branch is a mocked fixture |
| Large page/snapshot | Actual Chrome long page and >45KB failed response recover late redacted evidence by owner handle; GGUF reads retained large MCP text and recovers buried value | Controlled page/HTTP/MCP fixtures; model citation span inaccurate |
| Public research in Plan | Compiled graph and shared policy allow only selected trusted public web and deny MCP lookalikes | Scripted policy evidence; no production website research-quality claim |
| Browser handoff | Actual Harness takeover/return, Chrome manual local navigation, new epoch/snapshot, stale action refusal and fresh click pass | Service-driven manual fixture; not physical human input or live in-flight model draining |
| Form partial failure | First Unicode field changes, second invalid target fails, single input/invocation, warning and duplicate-call denial pass | Acknowledged failed/tool outcome with inspect/no-replay warning; no submission or uncertain acknowledgement claim |
| Desktop identity | Actual WinApp granted identity, wait/invoke/capture, revocation and cleanup pass; replaced-identity/timeout negatives pass | Replacement/timeout use service fixtures |
| Helper review | Compiled narrowing, frozen context/version, Ask inheritance, separately owned transcript and shared mutation lease pass | Scripted mechanism; not certified GGUF review judgment |
| Skills off/deselected | Native immutable package/off/deselection/resume/dependency regression guards pass | Real-model conditional selection is measured separately below |
| Cancellation/lost acknowledgement | Actual Windows tree cleanup, native stdio/browser completion/cancel, repeated cancellation and unknown-effect no-replay pass | Direct native/protocol plus scripted graph evidence; no model-quality claim |

The repeated GGUF comparison has two representative project tasks plus four supplements, not a twelve-task A/B/C model-quality certification. All twelve listed boundaries have executable or native evidence; screenshots, deterministic guards and model selection are distinct forms of proof.

## Atomic multi-edit benefit exercise

Twenty rotated repetitions per variant, through the actual compiled native graph, produced identical UTF-8 final bytes from identical original SHA-256 bytes. Native exact editing required two mutations; known-hash structured apply required one (three versus two total calls including their common read). The ordinary preview/apply path needs two calls and is not hidden by that comparison. An invalid second native edit retained the first change; structured validation left all original bytes unchanged. This establishes a useful atomic-failure boundary.

Host mutation median/range: native **1.97ms [1.45–3.65]**, structured **6.90ms [4.53–7.79]**. These are tiny host-operation measurements excluding model/authorization/common-read overhead, taken while backend validation ran. Atomic validation/fsync adds cost; no speed advantage or production latency claim follows. Ordinary templates retain native edits; multi-edit stays optional. Evidence: `.scratch/audit/structured-edit-benefit-20261001T010726Z/evidence.json` (40 valid runs plus two invalid-second controls; stable source fingerprint).

## Fixed-model discovery and cache comparison

The final comparison ran **36 native turns** on delivered revision `c18f85f`, with identical before/after backend fingerprint `4ee247afcaa7a551197cd570d9715149e4dab63cff4a4f514f4dc84013df3267`. Three rotated repetitions compared eager schemas, hybrid discovery with five project-tool pins, and fully deferred discovery over the same fifteen selected tools. Eager and hybrid completed **12/12** expected tasks each. Fully deferred completed **6/12**, all search tasks; its six write/repair attempts requested unnecessary user input and are failures, not fast completions. There were no failed/uncertain dispatched tool calls, six not-dispatched question outcomes and three empty discovery calls.

The existing Qwen3.5-4B-super-coder Q4_0 weights and CPU llama.cpp b11045 ran with GPU layers 0, context 16,384, eight threads, one slot, thinking off, temperature 0, seed 17, request output limit 224 and an explicit 8GiB RAM prefix cache. No user GPU model or saved setup was retuned. The fixture permits six tool calls and 420 seconds per attempt; these are evaluation bounds, not product defaults. Exact hashes, flags, requests and per-call native counters are recorded in `.scratch/audit/actual-model-20261001T011858Z/metadata.json` and `final-comparison-analysis.json`.

Fresh independent review reproduced every outcome/timing/schema/cache count from all 36 native records, 96 HTTP model requests and twelve final file snapshots: `.scratch/audit/final-model-review.md`. The frozen measured evaluator is retained under its recorded SHA-256. Its explicit application/project/server were scratch-owned, but an import-order mistake allowed the module-level application to reconcile normal deployment observations before selecting the scratch root. A later follow-up exposed the mistake through a denied atomic metadata replace before model startup; the scratch bootstrap is corrected and later probes verify its isolated root. This is an evaluation-isolation limitation, not an application fix or proof that the earlier import touched no production metadata. The separate protected-state recheck is recorded below.

| Identical task/turn | Eager seconds, median [range] | Hybrid seconds, median [range] | Fully deferred seconds, median [range] |
| --- | --- | --- | --- |
| Read input and write exact value, cold | 42.265 [42.171–42.329], 3/3 | 23.187 [23.062–23.250], 3/3 | 0/3; unnecessary user input |
| Repair and reread that file, warm | 7.984 [7.922–7.985], 3/3 | 7.343 [7.265–7.672], 3/3 | 0/3; unnecessary user input |
| Locate and read nested configuration, cold | 43.672 [43.656–43.750], 3/3 | 25.235 [25.218–25.672], 3/3 | 49.469 [20.781–49.797], 3/3 |
| Reread current configuration, warm | 6.203 [6.093–6.235], 3/3 | 6.250 [6.062–6.312], 3/3 | 13.782 [13.735–13.907], 3/3 |

First-request schema arrays were respectively **11,725/6,793/2,544 bytes** and **2,509/1,428/537 tokenizer tokens**. These token counts describe compact JSON tool arrays, not the total native rendered prompt contribution. Eager/hybrid used no discovery calls; deferred cold search used two per attempt and warm search none. First useful successful project-result median was 39/20/43 seconds for cold search, 39/20/not-completed for cold write, 5/5/not-completed for warm repair, and 4/5/12 for warm reread. This metric uses native result-event timestamps with one-second resolution; internal dispatch/effect onset is unavailable. It is distinct from first model output and does not certify answer usefulness.

Every cold first request followed an acknowledged owned slot erase and reported zero cached input tokens. The independent RAM prefix cache remained enabled: deferred cold search's third request processed 3,579 tokens with no cache in repetitions one/two, but only four tokens with 3,575 cached in repetition three, explaining its wide latency range. Per-call counters are authoritative. Warm tasks differ from cold tasks; comparisons above are between variants within identical task/turn, not a causal cold-versus-warm speed claim. Deferred warm repair follows unsuccessful creation, so its file remains absent: these are continuation failures of the same workflow, not three independently initialized repair trials. No pooled cross-variant latency comparison is used because deferred successes include only search. These CPU, two-task results establish neither GPU/other-model performance nor twelve-workflow quality.

Four separate native-model supplements preserve their individual outcomes. The real title-bearing MCP call preserved the required title and omitted payload, returning literal nested defaults. Large MCP text retained **135,021 UTF-8 bytes/132,521 characters**; the model used the authorized reader to retrieve the buried `opal` value. Actual Windows output retained **190,027 bytes/180,027 characters of decoded text**; the model retrieved `violet` and the correct exit0. This supplementary child's UTF-8 filler did not match the host-command owner's intentional locale decoding and contains mojibake; it does not prove exact Unicode fidelity. Earlier native Unicode tests are separate evidence, and the application host-locale contract was preserved. Both reader answers mislabeled excerpt context endpoints as exact match spans, so **value/exit acquisition passed, citation-coordinate accuracy did not**. Original native result metadata remains accurate. Evidence: `.scratch/audit/actual-model-20261001T013155Z/`.

The original broad-discovery supplement exhausted its 224-token response limit while composing the second call. The guard reported `incomplete_arguments/input` and executed no incomplete call. A separately labeled, verified-isolated functional follow-up kept the same source/model/runtime flags with request output limit768, followed the exact returned query/group cursor through two native calls, reached sixth operation `apply_edits`, and ended with `has_more: false`. It passed and its CPU process stopped. This follow-up is excluded from the fixed-profile timing matrix: `.scratch/audit/functional-cursor-20261001T014044Z/`. No saved product response limit was changed.

## Measured conditional skill selection

All nine skills were freshly rerun on delivered source with one positive and neighboring negative bounded GGUF probe: **14/18 intended conditional selections**, **7/9 positive original reads**, **7/9 negative nonactivations**, 13 native completions and five cancellations at the fixture's six-call bound. Independent review verified all 51 native model requests and exact selected original body/version/hash. The skill-probe tool ledger has 33 succeeded outcomes and five recoverable failed file reads, all in the overactivated project negative. A body read is not a completed workflow, and overall answer accuracy was not graded. Browser/delegate positives called domain tools despite planning-only instructions; those actions do not certify workflow success. Native completion also does not imply a correct answer: the Windows positive read the original but invented exit-code/command-change advice, and verification's negative did not give the requested OK-only reply. Version/authority safeguards passed independently regardless of model routing.

| Skill | Positive original read | Negative leaves body deferred | Observed limit |
| --- | --- | --- | --- |
| Project change | Yes | No | Unnecessary read for punctuation, then repeated file reads cancelled |
| Failure diagnosis | Yes | No | Negative cancelled at fixture bound |
| Windows execution | Yes | Yes | Original read, but invented exit-code/command-change advice |
| Verify delivery | No | Yes | Positive answered without original |
| Browser validation | Yes | Yes | Positive domain-call loop cancelled |
| Desktop validation | Yes | Yes | Conditional body selection passed; no end-to-end desktop judgment certification |
| Evidence research | No | Yes | Positive discovery loop cancelled |
| Delegate review | Yes | Yes | Positive invoked helper despite planning-only request, then cancelled |
| Memory curation | Yes | Yes | Negative made an unnecessary empty discovery call and unsupported error explanation; no proposal was submitted |

Final evidence: `.scratch/audit/actual-model-20261001T014303Z/skill-summary.json`, `skill-samples.json`, native run records and `.scratch/audit/model-evaluation-notes.md`. All eighteen use the same delivered backend fingerprint before/after, unchanged model/flags/prompts/224-token/six-call bounds, and the verified isolated module-import root. Ordered browser shutdown records zero remaining sessions; the owned Windows fixture and CPU server stopped. The earlier 12/18 partial aggregate crossed source changes and is superseded by this complete fresh run, not combined with it. These observations support deliberate skill selection; reliable model routing, planning answers or domain workflow effectiveness are not guaranteed.

## Established local delivery

Implementation [PR #216](https://github.com/Vidcar/thtaib/pull/216) is merged, main `c18f85fdc6d8526ee9cbb873adb6457970f0d56b`. The established launcher opened a fresh repository backend (PID 2852) and production Electron owner (PID 31504). Authenticated `/v1/agent-tools` exposes all new selected capabilities, an unauthenticated request is denied, and the normal data root remains unchanged. Built artifacts exactly match the isolated production UAT hashes. The original loaded deployment/profile was restored and confirmed healthy; no saved configuration was retuned. Launcher compatibility passed.

Strict before/after comparison passed with **no allowed exceptions or unexpected changes**: two conversations, five projects, seven agents/29 versions, defaults/preferences, nine runs, 86 retained assets/82 consumers, 11 model configurations, existing saved settings and **28 model files totaling 94,823,654,027 bytes** retain their saved-record hashes and model size/mtime identities. Evidence: `.scratch/lab-workbench/local-delivery/agent-tools-launch.json`, `agent-tools-comparison.json`, `agent-tools-refreshed-ui.png` and launcher log. This is saved/cached state preservation, not a hash of every model byte or a semantic model capability certification.

Independent read-only review reread all thirteen captured SQLite tables and confirmed their exact row/column hashes, including complete persisted Chat draft payloads. The pre-refresh native screenshot shows the visible Models editor saved with Save disabled. Hidden in-memory editors were not fingerprinted, so this does not prove every possible unsaved editor state. Accepted Knowledge has a separate file owner and was absent from the before snapshot: current API/disk agree on zero accepted entries/versions/resources, with one historical proposal and config, but their current fingerprints cannot retrospectively prove pre-refresh preservation. No loss was identified. These boundaries are recorded in `.scratch/audit/local-delivery-review.md` and its content-free JSON evidence; preservation claims are limited to the captured records/files and visible saved editor.

After the evaluator bootstrap mistake, a fresh independent, instrumented read-only check again found **zero differences** in the protected snapshot against both the original before and last after snapshots. Loaded bundle/profile/model identity/applied startup and current Knowledge hashes match the last review. Raw deployment creation instants, requested settings and saved profile snapshots also match; timezone representation differences were normalized as instants. Observational status/PID/health/props/cache/time metadata changes during ordinary live GETs and cannot be attributed retrospectively to the evaluator import. The failed atomic replace left no truncated target or remaining temp file. One earlier 15-second API timeout is preserved without a fabricated endpoint attribution; the final nine instrumented requests succeeded, with deployment GET0.164s and runtime/models GET8.343s. Evidence: `.scratch/audit/post-evaluation-preservation-review.md` and JSON. No saved-state restore or product change was made to manufacture this result.

The old shutdown HTTP request exceeded the client's 50-second wait. It was not replayed: process/listener inspection confirmed the original backend/router/model exited, the native model log recorded exit status zero, and only the exact saved idle Electron owner and its children were closed before a new launch. The subsequent launch/restoration and strict preservation passed. `agent-tools-refresh-stop.json` records the missing acknowledgement and observed settlement truthfully.

## Completed disposition and measured limits

All confirmed application defects and supported review findings are resolved. Every original finding/tool/settings item and additional capability proposal has a recorded disposition; nine optional skills and six reviewable templates are available. Main specifications are synced without losing previous requirements/scenarios. The implementation is merged and running locally; this report and completed change are archived under `openspec/changes/archive/2026-10-01-complete-agent-tools-audit/`.

The measured limitations are explicit rather than unresolved code work: conditional semantic navigation did not justify a new integration/index; this CPU model's fully deferred write workflow and four conditional skill choices failed; some planning/citation answers were inaccurate. Native/deterministic boundary proof does not certify all twelve domain workflows or model quality. Evaluation bootstrap, locale, cache, shutdown-acknowledgement and preservation-baseline limits are recorded above. No universal model tuning, expanded authority, unsupported lifecycle patch or fabricated evidence was used to turn these observations into a pass.
