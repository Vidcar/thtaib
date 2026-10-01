# Agent tools audit: verification and resolutions

Updated 1 October 2026. **Implementation verified; final model comparison and local delivery are active.**

Source: Dave's `thtaib-agent-tools-report-2026-09-30.md` (30 September 2026, pinned audit revision 0d3be38). Current implementation baseline: 21136f3; branch `codex/agent-tools-audit`. The attachment is evidence and recommendations, not execution authority. Dave separately authorized verification, fixes, upgrades and full validation.

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
| F09 schema/cache performance | Hypothesis; no measured defect | Fixed-model cold/warm eager/hybrid/deferred evaluation pending |
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

Deferred loading and a small task-specific pinned set remain the starting default. Pins do not grant capabilities. Chat owns Work/Plan, Ask/Full access and live Windows grants; templates state these prerequisites visibly. Model/context/sampling settings inherit the existing working setup. Review defaults off; memory, connections, helpers and embedding remain deliberate selections. Whole-task budgets remain optional and separate from operation acquisition/timeout limits. No discovery/cache reset policy is changed without the F09 measurements.

## Verification and actual evidence

Final backend delivery passed on frozen inputs: **1,410 default tests (one declared skip), 222 integration tests (three declared skips), and all four required real-model smoke tests**. No mandatory gate was bypassed. Report: `.scratch/verification/20261001T010138Z-a93fa98f/report.json`, input fingerprint `3195478bedb190e50fd62965242d2f92984d2b9a0c308e2990fc91de9e611e50`. The unchanged desktop build and generated-contract freshness passed in `.scratch/verification/20261001T002600Z-1945e98e/report.json`; that earlier combined report remains incomplete because its old smoke failed. Those failures were corrected and the entire affected backend delivery rerun passed. Synced specs/whitespace passed `.scratch/verification/20261001T010122Z-5f57f4c9/report.json`. Later report/checklist updates do not change the verified application inputs.

Fresh-context independent review cleared permission, persistence, lifecycle, projection and validation changes. The final 104-file source/test/contract/spec fingerprint is `c09219d89636afd40b6107251542c3b205b5a964658b5c7c1639e6cf5670c70b`. Review and reproducible reader: `.scratch/audit/independent-review.md`, `review-fingerprint.py`. All 101 previous requirements and 302 scenario names survive; seven requirements are added and two changed, with exact delta/main parity. Mandatory desktop guards remain intact; no remote CI was added.

Actual production Electron UAT passed Create-only project grants/exclusions, persistence/revocation across renderer reload, explicit bundled-skill installation without added authority, template model-draft preservation and saved agent/skill reopening. Nine screenshots, production artifact hashes and process identities are recorded under `.scratch/lab-workbench/agent-tools-native-20261001-010252/`. Native Chrome 154 / Playwright MCP 0.0.82 passed long-page/request evidence, credential redaction, media changes, partial form failure and fresh handoff targets. WinApp 0.7.0 passed selected-window identity, Unicode property wait, invoke/crop, revocation and owned cleanup. These tests used isolated data and owned workers.

Review and native probes found additional confirmed defects: repeated-cancellation project-lease cleanup, retaining model drafts through template Back/apply, before/after partial-deletion evidence, native custom-tool type/extras, correctable reference ranges, frozen resource identity schema and typed Windows admission. Each was corrected with affected negative/positive regressions. The required smoke also exposed a genuine continuation guard defect: canonical SDK text and mirrored tool-call blocks were rejected by a string-only template flag although the native endpoint accepts them. The corrected guard changes no checkpoints, admits only representable text/matching call duplicates, and still rejects unknown/audio/image/malformed/conflicting blocks and incomplete pairs. Actual write, same-thread native history, wire settings/readiness and projectless authority now pass.

Actual compiled browser completion/cancellation and deferred stdio MCP controls passed. The browser generator-close noise came from scratch evaluation teardown closing its owner loop first; the fixture now follows the already-correct production shutdown order. No unsupported application lifecycle patch was added. All evidence paths here are repository-root-relative development artifacts; they contain separate source/state fingerprints and are deliberately excluded from Git.

## Original twelve acceptance exercises

| Exercise | Completed evidence | Practical boundary |
| --- | --- | --- |
| Title-bearing MCP schema | Real pinned local MCP, native ToolNode and actual wire projection preserve title/default/nested schema; conforming scripted call passes | GGUF supplement pending; scripted selection is separate |
| Find the sixth relevant tool | Native discovery reaches all twelve matches by cursor/repeat, exact lookup and changed-selection denial | GGUF supplement pending |
| Read–edit–test–edit | Actual native filesystem and compiled scripted graph allow later repairs and reject competing same-batch writers | Intermediate file assertions; not a GGUF-selected test workflow |
| Long command output | Actual Windows processes retain late Unicode/error/exit evidence and clean owned children | GGUF continuation supplement pending; portable branch is a mocked fixture |
| Large page/snapshot | Actual Chrome long page and >45KB failed response recover late redacted evidence by owner handle | Controlled page/HTTP fixtures; model continuation supplement pending |
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

## Measured conditional skill selection

All nine skills have one positive and neighboring negative bounded GGUF probe: **12/18 intended conditional selections**, **6/9 positive original reads**, **6/9 negative nonactivations**, 14 native completions and four cancellations at the fixture's six-call bound. A body read is not a completed workflow, and answer accuracy was not graded. Browser/delegate positives called domain tools despite planning-only instructions; those actions do not certify workflow success. Version/authority safeguards passed independently regardless of model routing.

| Skill | Positive original read | Negative leaves body deferred | Observed limit |
| --- | --- | --- | --- |
| Project change | Yes | No | Unnecessary read for punctuation |
| Failure diagnosis | Yes | No | Negative cancelled at fixture bound |
| Windows execution | No | Yes | Positive included invented planning claims |
| Verify delivery | No | Yes | Positive answered without original |
| Browser validation | Yes | Yes | Positive domain-call loop cancelled |
| Desktop validation | Yes | No | Negative unnecessarily read original |
| Evidence research | No | Yes | Positive discovery loop cancelled |
| Delegate review | Yes | Yes | Positive invoked helper despite planning-only request, then cancelled |
| Memory curation | Yes | Yes | Negative read a project file, not the skill |

Evidence: `.scratch/audit/skill-probes-aggregate.json` and `.scratch/audit/model-evaluation-notes.md`. Earlier partial captures crossed source changes and are not final timing evidence. The last eight use equal before/after backend hashes with actual granted desktop admission and ordered worker cleanup. These observations support keeping skill selection deliberate; no guarantee of reliable routing across models is made.

## Remaining delivery work

Fixed-source eager/hybrid/deferred measurements and four supplements remain active. Merge/local refresh/preservation, final report and archive follow after those remaining checks. This intermediate report makes no claim that the established running desktop already uses the new code.
