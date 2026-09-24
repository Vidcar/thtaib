# Current handover

Updated 2026-09-24. The Deep Agents 0.7.18 simplification is merged in [PR #148](https://github.com/Vidcar/thtaib/pull/148). [PR #150](https://github.com/Vidcar/thtaib/pull/150) fixed Chat showing “Apply the changed model settings before sending a message” after a named model variant was applied, including in a new chat.

The backend now drops an inherited old deployment when a higher setup layer selects a model configuration, and matches deployments to a variant's actual startup recipe. Explicitly paired deployments still require safe application. Chat's Apply loads or reconfigures the selected managed model, binds the resulting deployment, reports failures, and no longer reselects or warms an unrelated deployment. The current spec and overlapping `consolidate-product-contract` delta describe this behavior.

Checks passed: backend default 729 tests (one skip), integration 188, desktop build, shared-contract freshness, and OpenSpec validation 13/13. After rebuilding and restarting the established app, applying `Qwen3.8 27B · 96k Q8 MTP variant` loaded `ctx_size=98304`, `spec_type=draft-mtp`, and Q8 key/value caches. The real model replied `READY` and `SECOND` in separate new chats without the warning. Chat is open on a blank conversation with that variant ready. Existing user chats and model weights were preserved.

Delivery is complete. The local checkout is on merged `main`, and the established app is open and ready for a new chat. Shell commands must use RTK.
