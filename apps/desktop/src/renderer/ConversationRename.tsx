import { useId, useMemo, useState } from "react";

import { conversationTitle } from "./display";
import type { ChatConversation } from "./types";
import "./ConversationRename.css";

const MAX_TITLE_LENGTH = 200;

export interface ConversationRenameProps {
  conversation: ChatConversation;
  currentTitle?: string;
  onRename: (title: string, conversation: ChatConversation) => Promise<void> | void;
  onCancel: () => void;
}

export function ConversationRename({ conversation, currentTitle, onRename, onCancel }: ConversationRenameProps) {
  const fallbackTitle = useMemo(() => currentTitle?.trim() || conversationTitle(conversation), [conversation, currentTitle]);
  const [title, setTitle] = useState(fallbackTitle);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputId = useId();
  const errorId = useId();
  const trimmed = title.trim();

  async function submit(): Promise<void> {
    const validation = validateTitle(trimmed);
    if (validation) {
      setError(validation);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onRename(trimmed, conversation);
    } catch (renameError) {
      setError(renameError instanceof Error ? renameError.message : String(renameError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="conversation-rename"
      aria-label={`Rename ${fallbackTitle}`}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onCancel();
        }
      }}
    >
      <label className="conversation-rename-field" htmlFor={inputId}>
        <span>Rename conversation</span>
        <input
          id={inputId}
          value={title}
          maxLength={MAX_TITLE_LENGTH}
          disabled={busy}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          autoFocus
          onChange={(event) => {
            setTitle(event.target.value);
            if (error) {
              setError("");
            }
          }}
        />
      </label>
      {error ? <p id={errorId} className="conversation-rename-error" role="alert">{error}</p> : null}
      <div className="conversation-rename-actions">
        <button type="button" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={busy || !trimmed || trimmed.length > MAX_TITLE_LENGTH}>
          {busy ? "Saving..." : "Save"}
        </button>
      </div>
    </form>
  );
}

function validateTitle(title: string): string | null {
  if (!title) {
    return "Enter a conversation name.";
  }
  if (title.length > MAX_TITLE_LENGTH) {
    return "Conversation names must be 200 characters or fewer.";
  }
  return null;
}
