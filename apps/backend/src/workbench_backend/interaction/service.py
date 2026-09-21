"""Local protocol commands delegate to the existing Chat/Harness owners."""
from __future__ import annotations

import copy
import json
import threading
from typing import Any
from uuid import uuid4, uuid5, NAMESPACE_URL

from pydantic import ValidationError
from langchain_protocol import Command, EventStreamRequest

from workbench_backend.agents.schemas import AgentRun, AgentStartRequest, InterruptDecisionRequest, UserAnswerRequest
from workbench_backend.chat.schemas import ChatStartRequest
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import WorkbenchError
from workbench_backend.inference.user_content import user_message_content
from workbench_backend.state.checkpointer import conversation_state
from workbench_backend.interaction.projection import archive_messages, event, native_event, partial_archive
from workbench_backend.interaction.schemas import WorkbenchInteractionMetadata


def invalid(message: str, code: str = "invalid_request", status: int = 400) -> WorkbenchError:
    return WorkbenchError(message, code=code, status_code=status)


def fields(value: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed:
        raise invalid(f"Unsupported {label} fields.")
    return value


class InteractionService:
    def __init__(self, store: Any, harness: Any, chat: Any) -> None:
        self.store = store
        self.harness_provider = harness
        self.chat_provider = chat
        # Serializes projection transactions, never holds a graph execution lock.
        self._projection_lock = threading.RLock()

    @property
    def harness(self) -> Any:
        return self.harness_provider()

    @property
    def chat(self) -> Any:
        return self.chat_provider()

    @staticmethod
    def _stored_run(run: AgentRun) -> dict[str, Any]:
        data = run.model_dump(mode="json")
        # Captured model context keeps its existing redaction/expiry owner.
        # Never create non-expiring copies in the protocol replay log.
        data["model_requests"] = []
        return data

    def display_values(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(snapshot)
        workbench = result.get("workbench", {})
        run = workbench.get("run")
        if run and run.get("id"):
            workbench["run"] = self.harness.get_run(run["id"]).model_dump(mode="json")
        result["workbench"] = WorkbenchInteractionMetadata.model_validate(workbench).model_dump(
            mode="json",
            exclude_none=True,
        )
        return result

    def binding(self, thread_id: str) -> dict[str, Any]:
        binding = self.store.get_interaction(thread_id)
        if binding is None:
            raise invalid("Unknown interaction thread.", "thread_missing", 404)
        return binding

    def register(self, body: dict[str, Any]) -> dict[str, str]:
        fields(body, {"source_surface", "conversation_id", "run_id"}, "registration")
        surface = body.get("source_surface")
        if surface == "chat" and isinstance(body.get("conversation_id"), str) and not body.get("run_id"):
            view = self.chat.get(body["conversation_id"])
            thread_id, graph_id = view.id, view.thread_id
            if not graph_id:
                raise invalid("Conversation has no saved execution thread.")
            prior = self.store.get_interaction(thread_id)
            if prior:
                self._repair_chat_projection(view, prior)
                return {"thread_id": thread_id}
            snapshot = self._seed_chat(view)
            self.store.register_interaction(thread_id, "chat", graph_id, view.id, snapshot)
            if view.current_run:
                self.observe(view.current_run, None)
        elif surface == "agent" and not body.get("conversation_id"):
            if body.get("run_id"):
                run = self.harness.get_run(body["run_id"])
                graph_id = run.thread_id or run.id
                prior = self.store.interaction_for_graph(graph_id)
                if prior:
                    return {"thread_id": prior["id"]}
                thread_id = f"interaction_{uuid4().hex}"
                retained = conversation_state(self.store.paths.checkpoints_db, graph_id)
                registered = self.store.register_interaction(thread_id, "agent", graph_id, None,
                    {"messages": archive_messages([], retained.get("messages", [])), "workbench": {"run": None}})
                thread_id = registered["id"]
                self.observe(run, None)
            else:
                thread_id = f"interaction_{uuid4().hex}"
                self.store.register_interaction(thread_id, "agent", f"thread_{uuid4().hex}", None,
                                                {"messages": [], "workbench": {"run": None}})
        else:
            raise invalid("Choose an existing Chat conversation or an Agent run thread.")
        return {"thread_id": thread_id}

    def _seed_chat(self, view: Any) -> dict[str, Any]:
        retained = conversation_state(self.store.paths.checkpoints_db, view.thread_id)
        checkpoint_messages = archive_messages([], retained.get("messages", []))
        return self._seed_chat_archive(view, checkpoint_messages)

    def _seed_chat_archive(self, view: Any, checkpoint_messages: list[dict[str, Any]]) -> dict[str, Any]:
        archive: list[dict[str, Any]] = []
        if view.history_replaced:
            for index, item in enumerate(view.transcript):
                kind = {"user": "human", "assistant": "ai", "system": "system"}.get(item.role)
                if kind is None:
                    continue
                archive.append({"id": item.id or str(uuid5(NAMESPACE_URL, f"{view.id}:{index}:{item.role}")),
                                "type": kind, "content": item.content_blocks or item.content})
            return {"messages": archive, "workbench": {"run": None, "conversation_id": view.id, "archive_seed_version": 2,
                "display_excluded_message_ids": [m["id"] for m in checkpoint_messages],
                "display_hidden_run_id": view.current_run_id}}
        matches = self._align_checkpoint_suffix(view, checkpoint_messages)
        checkpoint_cursor = 0
        # One-time display migration: match retained identities in transcript
        # order. Legacy rows without IDs are aligned from the retained suffix so
        # repeated equal text does not steal a newer runtime identity.
        for index, item in enumerate(view.transcript):
            kind = {"user": "human", "assistant": "ai", "system": "system"}.get(item.role)
            if kind is None:
                continue
            checkpoint_index = matches.get(index)
            if checkpoint_index is None:
                archive.append({"id": item.id or str(uuid5(NAMESPACE_URL, f"{view.id}:{index}:{item.role}")),
                                "type": kind, "content": item.content_blocks or item.content})
                continue
            archive = archive_messages(archive, checkpoint_messages[checkpoint_cursor:checkpoint_index + 1])
            checkpoint_cursor = checkpoint_index + 1
        workbench: dict[str, Any] = {"run": None, "conversation_id": view.id, "archive_seed_version": 2}
        if archive and checkpoint_messages and not matches:
            # No defensible correspondence: retain the readable archive rather
            # than duplicate or invent positions for compacted execution rows.
            # Subsequent values must not reintroduce those ambiguous old rows.
            workbench["display_excluded_message_ids"] = [m["id"] for m in checkpoint_messages]
        else:
            archive = archive_messages(archive, checkpoint_messages[checkpoint_cursor:])
        return {"messages": archive, "workbench": workbench}

    def _repair_chat_projection(self, view: Any, binding: dict[str, Any]) -> None:
        with self._projection_lock:
            binding = self.store.get_interaction(binding["id"]) or binding
            if binding.get("surface") != "chat" or view.history_replaced:
                return
            snapshot = copy.deepcopy(binding["snapshot"])
            workbench = snapshot.get("workbench", {})
            if (workbench.get("archive_seed_version") == 2 or
                    workbench.get("display_cutover_seq") or workbench.get("display_hidden_run_id") or
                    workbench.get("display_excluded_message_ids")):
                return
            messages = self._repaired_archive(view, snapshot.get("messages", []))
            if messages is None:
                return
            repaired = copy.deepcopy(snapshot)
            repaired["messages"] = messages
            repaired.setdefault("workbench", {})["archive_seed_version"] = 2
            self.store.append_interaction(binding["id"], [event("values", repaired)], snapshot=repaired,
                                          run_id=binding.get("run_id"))

    def _repaired_archive(self, view: Any, existing: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Recognize the old seed's exact provenance, never a text permutation.

        Display-only UUIDs identify original transcript positions. The faulty
        algorithm placed those rows first and appended the retained checkpoint.
        Reconstruct that algorithm using the durable projection's own complete
        messages; require byte-equivalent public records before replacing a
        prefix. Later rows and all metadata remain untouched. No checkpoint read
        is needed, so compaction since registration does not destroy the proof.
        """
        display_ids = {
            str(uuid5(NAMESPACE_URL, f"{view.id}:{index}:{item.role}"))
            for index, item in enumerate(view.transcript) if not item.id
        }
        if not any(item.get("id") in display_ids for item in existing):
            return None
        boundaries = [index + 1 for index, item in enumerate(existing)
                      if item.get("type") in {"human", "ai", "system"}
                      and not item.get("tool_calls")]
        for count in range(min(len(view.transcript), len(boundaries)), 1, -1):
            size = boundaries[count - 1]
            prefix = existing[:size]
            retained = [item for item in prefix if item.get("id") not in display_ids]
            source = view.model_copy(update={"transcript": view.transcript[:count]})
            if not self._align_checkpoint_suffix(source, retained):
                continue
            old = self._legacy_seed_archive(source, retained)
            if old != prefix:
                continue
            repaired = self._seed_chat_archive(source, retained)["messages"]
            if repaired == prefix:
                return None
            # New display identities must not collide with later durable rows.
            if {m.get("id") for m in repaired} & {m.get("id") for m in existing[size:]}:
                continue
            return repaired + existing[size:]
        return None

    def _legacy_seed_archive(self, view: Any, checkpoint: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fingerprint the delivered faulty algorithm solely for narrow repair."""
        claimed: set[str] = set()
        archive = []
        for index, item in enumerate(view.transcript):
            kind = {"user": "human", "assistant": "ai", "system": "system"}[item.role]
            match = next((m for m in checkpoint if m["id"] not in claimed and
                          m["type"] == kind and self._text(m.get("content")) == item.content), None)
            ident = item.id or (match["id"] if match else str(uuid5(NAMESPACE_URL, f"{view.id}:{index}:{item.role}")))
            claimed.add(ident)
            archive.append({"id": ident, "type": kind, "content": item.content_blocks or item.content})
        checkpoint_ids = {m["id"] for m in checkpoint}
        return archive_messages([m for m in archive if m["id"] not in checkpoint_ids], checkpoint)

    def _align_checkpoint_suffix(self, view: Any, checkpoint_messages: list[dict[str, Any]]) -> dict[int, int]:
        transcript = []
        for index, item in enumerate(view.transcript):
            kind = {"user": "human", "assistant": "ai", "system": "system"}.get(item.role)
            if kind is not None:
                transcript.append((index, kind, self._content_key(item.content_blocks or item.content), item.id))
        checkpoint = [
            (index, message.get("type"), self._content_key(message.get("content")), message.get("id"))
            for index, message in enumerate(checkpoint_messages)
            if message.get("type") in {"human", "ai", "system"} and not (
                message.get("type") == "ai" and message.get("tool_calls")
            )
        ]
        # Explicit identities remain authoritative even when the retained tail
        # is newer than the readable archive (for example during generation).
        matches: dict[int, int] = {}
        cursor = -1
        for source_index, kind, _content, ident in transcript:
            if not ident:
                continue
            found = next((i for i, target_kind, _target_content, target_ident in checkpoint
                          if i > cursor and target_ident == ident and target_kind == kind), None)
            if found is not None:
                matches[source_index] = found
                cursor = found
        if not transcript or not checkpoint:
            return matches
        suffix: dict[int, int] = {}
        transcript_index = len(transcript) - 1
        checkpoint_index = len(checkpoint) - 1
        while transcript_index >= 0 and checkpoint_index >= 0:
            source_index, kind, content, ident = transcript[transcript_index]
            target_index, target_kind, target_content, target_ident = checkpoint[checkpoint_index]
            if kind != target_kind or content != target_content:
                break
            if ident and ident != target_ident:
                break
            suffix[source_index] = target_index
            transcript_index -= 1
            checkpoint_index -= 1
        if checkpoint_index >= 0:
            return matches
        return suffix

    @staticmethod
    def _content_key(content: Any) -> str:
        return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def replace_chat_display_archive(self, view: Any) -> None:
        """Project an authorized display-only edit without changing execution."""
        with self._projection_lock:
            binding = self.store.get_interaction(view.id)
            if binding is None:
                return
            snapshot = copy.deepcopy(binding["snapshot"])
            seeded = self._seed_chat(view)
            workbench = snapshot.setdefault("workbench", {})
            excluded = set(workbench.get("display_excluded_message_ids", []))
            excluded.update(m["id"] for m in snapshot.get("messages", []) if m.get("id"))
            excluded.update(seeded["workbench"].get("display_excluded_message_ids", []))
            workbench.update({"display_excluded_message_ids": sorted(excluded),
                              "display_hidden_run_id": view.current_run_id,
                              "display_cutover_seq": binding["seq"] + 1})
            snapshot["messages"] = seeded["messages"]
            self.store.append_interaction(view.id, [event("values", snapshot)], snapshot=snapshot)

    @staticmethod
    def _text(content: Any) -> str:
        if isinstance(content, str):
            return content
        return "".join(block.get("text", "") for block in content or [] if isinstance(block, dict) and block.get("type") == "text")

    def observe(self, run: AgentRun, raw: dict[str, Any] | None) -> None:
        with self._projection_lock:
            binding = self.store.interaction_for_graph(run.thread_id or run.id)
            if binding is None:
                return
            snapshot = copy.deepcopy(binding["snapshot"])
            outgoing = []
            if raw is not None:
                params = raw.get("params", {})
                namespace = params.get("namespace", [])
                display_hidden = snapshot.get("workbench", {}).get("display_hidden_run_id") == run.id
                if display_hidden and raw.get("method") in {"messages", "tools"}:
                    return
                if raw.get("method") == "values":
                    data = params.get("data", {})
                    if not namespace:
                        excluded = set(snapshot.get("workbench", {}).get("display_excluded_message_ids", []))
                        incoming = archive_messages([], data.get("messages", []))
                        if display_hidden:
                            excluded.update(m["id"] for m in incoming)
                            snapshot["workbench"]["display_excluded_message_ids"] = sorted(excluded)
                        snapshot["messages"] = archive_messages(snapshot.get("messages", []),
                            [m for m in incoming if m["id"] not in excluded])
                    else:
                        outgoing.append(event("values", {"messages": archive_messages([], data.get("messages", []))}, namespace))
                projected = native_event(raw)
                for item in projected:
                    if item["method"] == "input.requested":
                        p = item["params"]
                        snapshot["__interrupt__"] = [{"id": p["data"]["interrupt_id"], "value": p["data"]["payload"], "namespace": p["namespace"]}]
                        snapshot["workbench"]["interrupt_run_id"] = run.id
                outgoing.extend(projected)
                if raw.get("method") == "values" and not namespace:
                    outgoing.insert(0, event("values", snapshot))
            else:
                previous = snapshot.get("workbench", {}).get("run") or {}
                snapshot.setdefault("workbench", {}).update({"run": self._stored_run(run), "conversation_id": binding["conversation_id"]})
                if previous.get("id") != run.id:
                    snapshot["workbench"]["run_started_seq"] = binding["seq"]
                    snapshot["workbench"].pop("recovery", None)
                if run.input_message_id and snapshot["workbench"].get("display_hidden_run_id") != run.id:
                    snapshot["messages"] = archive_messages(snapshot.get("messages", []), [{
                        "type": "human", "id": run.input_message_id, "content": user_message_content(run.task, run.content_blocks),
                    }])
                if not run.pending_interrupt and (previous.get("pending_interrupt") or previous.get("id") != run.id or not is_run_lifecycle_live(run.status)):
                    snapshot["__interrupt__"] = []
                    snapshot["workbench"].pop("interrupt_run_id", None)
                if not is_run_lifecycle_live(run.status) and previous.get("status") not in {"completed", "failed", "cancelled"} and snapshot["workbench"].get("display_hidden_run_id") != run.id:
                    partials, incomplete = partial_archive(self.replay(binding["id"], snapshot["workbench"].get("run_started_seq", 0), binding["seq"]))
                    snapshot["messages"] = archive_messages(snapshot.get("messages", []), partials)
                    snapshot["workbench"]["incomplete_message_ids"] = sorted(
                        set(snapshot["workbench"].get("incomplete_message_ids", [])) | set(incomplete))
                outgoing.append(event("values", snapshot))
                state = self._lifecycle(run)
                prior_state = self._lifecycle_dict(previous)
                if state != prior_state or previous.get("id") != run.id:
                    outgoing.append(event("lifecycle", {"event": state, "run_id": run.id,
                        "graph_name": "local-ai-workbench", "app_status": run.status.value,
                        **({"error": run.error} if run.error else {})}))
            self.store.append_interaction(binding["id"], outgoing, snapshot=snapshot, run_id=run.id)

    def replay(self, thread_id: str, since: int, through: int):
        while since < through:
            page = self.store.interaction_events_after(thread_id, since)
            if not page:
                return
            for item in page:
                if item["seq"] > through:
                    return
                since = item["seq"]
                yield item

    def resynchronize(self, thread_id: str) -> int:
        self.state(thread_id)
        with self._projection_lock:
            binding = self.binding(thread_id)
            snapshot = copy.deepcopy(binding["snapshot"])
            snapshot.setdefault("workbench", {})["recovery"] = {
                "kind": "replay_gap", "message": "Live updates were interrupted. Saved output has been reloaded; no action was repeated.",
            }
            outgoing = [event("values", snapshot)]
            run = snapshot["workbench"].get("run")
            if run:
                outgoing.append(event("lifecycle", {"event": self._lifecycle_dict(run), "run_id": run["id"], "app_status": run["status"]}))
            self.store.append_interaction(thread_id, outgoing, snapshot=snapshot)
            return binding["seq"]

    @staticmethod
    def _lifecycle(run: AgentRun) -> str:
        return InteractionService._lifecycle_dict(run.model_dump(mode="json"))

    @staticmethod
    def _lifecycle_dict(run: dict[str, Any]) -> str:
        if run.get("pending_interrupt") and run.get("status") != "cancel_requested":
            return "interrupted"
        if run.get("status") == "failed":
            return "failed"
        if run.get("status") in {"completed", "cancelled"}:
            return "completed"
        return "running"

    def state(self, thread_id: str) -> dict[str, Any]:
        binding = self.binding(thread_id)
        if binding["run_id"]:
            # Existing recovery owner reconciles orphaned workers before we
            # advertise finality. It never invokes the model on a state read.
            current = self.harness.get_run(binding["run_id"])
            if self._stored_run(current) != binding["snapshot"].get("workbench", {}).get("run"):
                self.observe(current, None)
                binding = self.binding(thread_id)
        values = self.display_values(binding["snapshot"])
        run = values.get("workbench", {}).get("run") or {}
        active = run.get("status") in {"queued", "running", "cancel_requested"}
        interrupts = values.get("__interrupt__", [])
        return {"values": values, "next": ["input.respond" if interrupts else "running"] if active else [],
                "tasks": [{"interrupts": interrupts}] if interrupts else [],
                "interaction_cursor": binding["seq"]}

    def command(self, thread_id: str, body: Command) -> dict[str, Any]:
        fields(body, {"id", "method", "params"}, "command")
        if not isinstance(body.get("id"), (str, int)) or isinstance(body.get("id"), bool):
            raise invalid("A command correlation ID is required.")
        binding = self.binding(thread_id)
        method = body.get("method")
        if method not in {"run.start", "input.respond"}:
            raise invalid("This local backend does not support that protocol command.", "not_supported")
        # Existing per-conversation lock also serializes standalone binding
        # commands. No graph worker needs this lock to publish its output.
        with self.store.conversation_lock(thread_id):
            binding = self.binding(thread_id)
            if method == "run.start":
                return self._start(binding, body.get("params"))
            return self._respond(binding, body.get("params"))

    def _start(self, binding: dict[str, Any], params: Any) -> dict[str, Any]:
        params = fields(params, {"assistant_id", "input", "config", "metadata", "multitaskStrategy"}, "run.start")
        self._validate_config(binding, params.get("config"))
        if params.get("multitaskStrategy") not in {None, "reject"}:
            raise invalid("This local backend only supports reject-while-active.", "not_supported")
        if params.get("assistant_id") not in {None, "_", "local-ai-workbench"}:
            raise invalid("Unknown local assistant.")
        metadata = fields(params.get("metadata", {}), {"workbench"}, "metadata")
        setup = dict(metadata.get("workbench", {}))
        if {"task", "thread_id", "source_surface", "input_message_id", "resume_checkpoint_id"} & set(setup):
            raise invalid("Thread ownership and message identity are assigned by the local binding.")
        input_value = fields(params.get("input"), {"messages"}, "input")
        messages = input_value.get("messages")
        if not isinstance(messages, list) or len(messages) != 1:
            raise invalid("Submit exactly one new user message.")
        message = fields(messages[0], {"type", "role", "id", "content", "additional_kwargs", "response_metadata"}, "user message")
        # The SDK's optimistic HumanMessage serializes these empty containers.
        # They carry no application authority and nonempty values are rejected.
        for key in ("additional_kwargs", "response_metadata"):
            if key in message and message[key] != {}:
                raise invalid(f"User message {key} must be empty.")
        if message.get("type", message.get("role")) not in {"human", "user"}:
            raise invalid("Only user input can start a run.")
        ident = message.get("id") or str(uuid4())
        if not isinstance(ident, str) or not ident or len(ident) > 200:
            raise invalid("Invalid user message identity.")
        if any(m.get("id") == ident for m in binding["snapshot"].get("messages", [])):
            raise invalid("This input was already submitted.", "duplicate_input", 409)
        if binding["run_id"] and is_run_lifecycle_live(self.harness.get_run(binding["run_id"]).status):
            raise invalid("Wait for the current run to finish or cancel it.", "run_active", 409)
        content = message.get("content")
        if not isinstance(content, (str, list)):
            raise invalid("User input must contain text or supported content blocks.")
        setup.update(task=self._text(content), input_message_id=ident)
        if isinstance(content, list):
            if "content_blocks" in setup:
                raise invalid("Content blocks were supplied twice.")
            setup["content_blocks"] = content
            # The blocks already carry the user's text in its original order.
            # Adding that text again as task would duplicate it in inference.
            setup["task"] = ""
        if binding["surface"] == "chat":
            result = self.chat.start(binding["conversation_id"], ChatStartRequest.model_validate(setup))
            run = result.current_run
        else:
            setup.update(thread_id=binding["graph_thread_id"], source_surface="agent-run")
            run = self.harness.start(AgentStartRequest.model_validate(setup))
        return {"run_id": run.id, "applied_through_seq": binding["seq"]}

    def _respond(self, binding: dict[str, Any], params: Any) -> dict[str, Any]:
        params = fields(params, {"namespace", "interrupt_id", "response", "config", "metadata"}, "input.respond")
        self._validate_config(binding, params.get("config"))
        if params.get("metadata"):
            raise invalid("Interrupt responses cannot change run configuration.")
        snapshot = binding["snapshot"]
        interrupts = snapshot.get("__interrupt__", [])
        selected = next((item for item in interrupts if item["id"] == params.get("interrupt_id") and item.get("namespace", []) == params.get("namespace", [])), None)
        if not selected or snapshot.get("workbench", {}).get("interrupt_run_id") != binding["run_id"]:
            raise invalid("This approval is stale or belongs to another run.", "stale_interrupt", 409)
        response = fields(params.get("response"), {"decisions", "answer", "cancelled"}, "interrupt response")
        for decision in response.get("decisions", []):
            fields(decision, {"type", "message", "scope"}, "interrupt decision")
        identified_response = {
            **response,
            "interrupt_id": params.get("interrupt_id"),
            "namespace": params.get("namespace", []),
        }
        request = (
            UserAnswerRequest.model_validate(identified_response)
            if "answer" in response or "cancelled" in response
            else InterruptDecisionRequest.model_validate(identified_response)
        )
        run = self.harness.resume_interrupt(binding["run_id"], request, require_interrupt_identity=True)
        return {"run_id": run.id, "applied_through_seq": binding["seq"]}

    @staticmethod
    def _validate_config(binding: dict[str, Any], config: Any) -> None:
        if config in (None, {}):
            return
        # The released React coordinator inserts the protocol binding's ID.
        # Validate it, then route to the server-owned graph ID; never forward
        # configurable fields into LangGraph or permit a checkpoint override.
        if config != {"configurable": {"thread_id": binding["id"]}}:
            raise invalid("Graph configuration overrides are not supported.")

    def subscription(self, thread_id: str, body: EventStreamRequest) -> dict[str, Any]:
        self.binding(thread_id)
        fields(body, {"channels", "namespaces", "depth", "since"}, "subscription")
        channels = body.get("channels")
        allowed = {"values", "messages", "tools", "lifecycle", "input", "checkpoints"}
        if not isinstance(channels, list) or not channels or any(c not in allowed for c in channels):
            raise invalid("Unsupported subscription channel.", "not_supported")
        namespaces = body.get("namespaces", [[]])
        if not isinstance(namespaces, list) or any(not isinstance(ns, list) or any(not isinstance(n, str) for n in ns) for ns in namespaces):
            raise invalid("Invalid namespace filters.")
        for key in ("depth", "since"):
            value = body.get(key)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise invalid(f"Invalid {key}.")
        return dict(body)

    @staticmethod
    def matches(item: dict[str, Any], body: dict[str, Any]) -> bool:
        method = item["method"]
        if ("input" if method.startswith("input.") else method) not in body["channels"]:
            return False
        namespace = item["params"].get("namespace", [])
        return any(namespace[:len(prefix)] == prefix and
                   (body.get("depth") is None or len(namespace) - len(prefix) <= body["depth"])
                   for prefix in (body.get("namespaces") or [[]]))
