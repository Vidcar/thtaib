import type { PendingInterrupt } from "./types";

export function InterruptApproval(props: {
  pending: PendingInterrupt;
  busy?: boolean;
  onDecide: (type: "approve" | "reject") => void;
}) {
  const { pending, busy, onDecide } = props;
  return (
    <div className="card">
      <h3>Host shell approval</h3>
      <p className="hint">{pending.note}</p>
      <p>
        environment: {pending.environment} · isolation: {pending.isolation} · kind: {pending.kind}
      </p>
      <pre className="json">{JSON.stringify(pending.action_requests, null, 2)}</pre>
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => onDecide("approve")}>
          Approve
        </button>
        <button type="button" disabled={busy} onClick={() => onDecide("reject")}>
          Deny
        </button>
      </div>
    </div>
  );
}
