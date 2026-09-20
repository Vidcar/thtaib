import { interruptCommand } from "./display";
import type { PendingInterrupt, PendingInterruptAction } from "./types";

function actionTitle(action: PendingInterruptAction): string {
  if (action.description?.trim()) {
    return action.description;
  }
  return action.name;
}

function actionWorkingFolder(action: PendingInterruptAction): string | null {
  const cwd = action.args.cwd ?? action.args.working_directory ?? action.args.workdir;
  return typeof cwd === "string" && cwd.trim() ? cwd : null;
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
        This command will run on this PC. Approve it only if it matches what you asked the assistant
        to do.
      </p>
      <ul className="plain-list">
        {pending.action_requests.map((action, index) => {
          const command = interruptCommand(action);
          const workingFolder = actionWorkingFolder(action);
          return (
            <li key={`${action.name}-${index}`} className="approval-action">
              <strong>{actionTitle(action)}</strong>
              {workingFolder ? (
                <p className="hint">
                  Working folder: <code>{workingFolder}</code>
                </p>
              ) : null}
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
