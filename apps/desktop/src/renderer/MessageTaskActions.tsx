import { Icon, type IconName } from "./Icon";
import { HoverHelp } from "./HoverHelp";

export function MessageTaskActions({ runId, held, onRetry, onEdit }: {
  runId: string;
  held: string | null;
  onRetry: () => void;
  onEdit: () => void;
}) {
  return (
    <div className="message-task-actions" role="group" aria-label="Message actions">
      <RewindButton label="Retry" icon="refresh" held={held} onActivate={onRetry} />
      <RewindButton label="Edit" icon="edit" held={held} runId={runId} onActivate={onEdit} />
    </div>
  );
}

function RewindButton({ label, icon, held, runId, onActivate }: {
  label: string;
  icon: IconName;
  held: string | null;
  runId?: string;
  onActivate: () => void;
}) {
  return (
    <HoverHelp
      label={label}
      held={held}
      onActivate={onActivate}
      editRunId={runId}
      triggerClassName="icon-button"
      triggerContent={<Icon name={icon} size={14} />}
      bubbleClassName="rewind-tooltip"
      placement="above"
      clearanceSelector=".chat-header"
      visibleFocusOnly
    >
      {held}
    </HoverHelp>
  );
}
