import { interruptCommand } from "./display";
import type { PendingInterrupt, PendingInterruptAction } from "./types";

function actionTitle(action: PendingInterruptAction): string {
  if (action.description?.trim()) {
    return action.description;
  }
  return action.name;
}

export function InterruptApproval(props: {
  pending: PendingInterrupt;
  busy?: boolean;
  onDecide: (type: "approve" | "reject") => void;
}) {
  const { pending, busy, onDecide } = props;
  return (
    <div className="approval-card" role="alertdialog" aria-labelledby="approval-title">
      <h3 id="approval-title">Approve this command?</h3>
      <p className="notice notice-warn">
        This runs on this PC with no isolation
        {pending.environment === "windows_host_shell" ? " (Windows host shell)" : ""}. It is not a
        saved approvals inbox.
      </p>
      <ul className="plain-list">
        {pending.action_requests.map((action, index) => {
          const command = interruptCommand(action);
          return (
            <li key={`${action.name}-${index}`} className="approval-action">
              <strong>{actionTitle(action)}</strong>
              {command ? <pre className="command">{command}</pre> : null}
              {!command && Object.keys(action.args).length > 0 ? (
                <dl className="meta compact">
                  {Object.entries(action.args).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>
                        <code>{typeof value === "string" ? value : JSON.stringify(value)}</code>
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </li>
          );
        })}
      </ul>
      {pending.note ? <p className="hint">{pending.note}</p> : null}
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => onDecide("approve")}>
          Approve
        </button>
        <button type="button" className="danger" disabled={busy} onClick={() => onDecide("reject")}>
          Deny
        </button>
      </div>
    </div>
  );
}
