"""Observe persisted terminal runs outside harness locks; never execute an agent loop."""
import logging
import queue
import threading

from workbench_backend.state.backup import BackupError

log = logging.getLogger(__name__)


class ChatCoordinator:
    def __init__(self, application):
        self.application = application
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._work, name="chat-terminal-reconciliation", daemon=True)
        self.thread.start()

    def observe(self, run):
        if run.source_surface == "chat" and run.status in {"completed", "failed", "cancelled"}:
            self.events.put(run.id)

    def _work(self):
        state = self.application.state
        while not self.closed.is_set():
            try:
                run_id = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                with state.maintenance_gate.mutation():
                    run = state.harness.get_run(run_id)
                    for conversation in state.chat.store.list_conversations(include_archived=True):
                        if run.id in conversation.run_ids and conversation.current_run_id == run.id:
                            state.asset_lifecycle.collect_verified_outputs_for_run(conversation.id, run.id)
                    state.chat.observe_terminal_run(run)
            except BackupError:
                if not self.closed.wait(0.2):
                    self.events.put(run_id)
            except Exception:
                log.exception("Chat terminal reconciliation failed for %s; pending work remains durable", run_id)
            finally:
                self.events.task_done()

    def close(self):
        self.closed.set()
        self.thread.join(timeout=20)
        if self.thread.is_alive():
            raise RuntimeError("Chat reconciliation is still using the application store")
