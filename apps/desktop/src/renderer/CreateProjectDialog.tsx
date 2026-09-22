import { useEffect, useState } from "react";
import { CompactDialog } from "./CompactDialog";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { PathField } from "./PathField";
import { workspaceApi, type ProjectRecord } from "./workspaceApi";

export function CreateProjectDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (project: ProjectRecord) => void }) {
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
  }, [open]);

  if (!open) return null;

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
    <CompactDialog title="Create project" labelledBy="create-project-title" busy={busy} onClose={onClose}>
      <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <label>Project name<input maxLength={200} required value={name} disabled={busy} onChange={event => setName(event.target.value)} placeholder="Copenhagen Trip" /></label>
        <PathField
          kind="folder"
          label="Folder"
          value={path}
          required
          disabled={busy}
          placeholder="Choose an existing folder"
          buttonLabel="Choose folder"
          icon="folder"
          onChange={setPath}
          onPicked={selected => setName(current => current.trim() ? current : selected.replace(/\\/g, "/").split("/").filter(Boolean).at(-1) ?? "")}
          onError={failure => setError(errorMessage(failure))}
        />
        <p className="hint">A project keeps chats for this folder together. It does not change memory or file permissions, and it does not delete the folder if you remove the project later.</p>
        {error ? <Notice tone="error" role="alert">{error}</Notice> : null}
        <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy || !name.trim() || !path.trim()}>{busy ? "Creating…" : "Create project"}</button></footer>
      </form>
    </CompactDialog>
  );
}
