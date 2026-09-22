import { useEffect, useRef, useState } from "react";
import { errorMessage } from "./errors";
import { Icon } from "./Icon";
import { workspaceApi, type ProjectRecord } from "./workspaceApi";

export function CreateProjectDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (project: ProjectRecord) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName("");
    setPath("");
    setError("");
    setBusy(false);
    dialog.current?.showModal();
  }, [open]);

  if (!open) return null;

  async function browse() {
    try {
      const selected = await window.workbench?.selectPath?.("folder");
      if (!selected) return;
      setPath(selected);
      setName(current => current.trim() ? current : selected.replace(/\\/g, "/").split("/").filter(Boolean).at(-1) ?? "");
    } catch (failure) {
      setError(errorMessage(failure));
    }
  }

  async function submit() {
    if (!name.trim() || !path.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const project = await workspaceApi.createProject(path.trim(), name.trim());
      onCreated(project);
      onClose();
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} className="compact-dialog" aria-labelledby="create-project-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }} onClose={onClose}>
      <header>
        <h3 id="create-project-title">Create project</h3>
        <button type="button" className="icon-button" aria-label="Close" disabled={busy} onClick={onClose}><Icon name="close" /></button>
      </header>
      <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <label>Project name<input maxLength={200} required value={name} disabled={busy} onChange={event => setName(event.target.value)} placeholder="Copenhagen Trip" /></label>
        <label>Folder<input required value={path} disabled={busy} onChange={event => setPath(event.target.value)} placeholder="Choose an existing folder" /></label>
        <button type="button" disabled={busy || !window.workbench?.selectPath} onClick={() => void browse()}><Icon name="folder" size={15} /> Choose folder</button>
        <p className="hint">A project keeps chats for this folder together. It does not change memory or file permissions, and it does not delete the folder if you remove the project later.</p>
        {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
        <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy || !name.trim() || !path.trim()}>{busy ? "Creating…" : "Create project"}</button></footer>
      </form>
    </dialog>
  );
}
