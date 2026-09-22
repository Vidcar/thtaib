import { useEffect, useMemo, useState } from "react";

import { interruptCommand } from "./display";
import { PathBrowseButton } from "./PathField";
import type { PendingInterrupt, PendingInterruptAction, UserQuestion } from "./types";

type ApprovalType = "approve" | "reject";
type ApprovalScope = "once" | "session" | "always";

export type InterruptResponsePayload =
  | { decisions: Array<{ type: ApprovalType; scope: ApprovalScope; message?: string }> }
  | { answer: string; cancelled?: boolean };

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

function defaultDecision(action: PendingInterruptAction): ApprovalType {
  return action.allowed_decisions.includes("approve") ? "approve" : "reject";
}

function answerTypeLabel(question: UserQuestion): string {
  switch (question.answer_type) {
    case "choice":
      return "Choose an answer";
    case "file":
      return "Select a file";
    case "folder":
      return "Select a folder";
    case "text":
      return "Answer";
    default: {
      const unexpected: never = question.answer_type;
      return unexpected;
    }
  }
}

function NativePathSelector(props: {
  answerType: "file" | "folder";
  busy?: boolean;
  onSelect: (selected: string) => void;
}) {
  const { answerType, busy, onSelect } = props;
  return <PathBrowseButton kind={answerType} label="Browse" disabled={busy} onPicked={onSelect} />;
}

export function InterruptApproval(props: {
  pending: PendingInterrupt;
  busy?: boolean;
  onRespond: (payload: InterruptResponsePayload) => void;
}) {
  const { pending, busy, onRespond } = props;
  const decisionSignature = useMemo(
    () => pending.action_requests.map((action) => `${action.name}:${action.allowed_decisions.join(",")}`).join("|"),
    [pending.action_requests],
  );
  const [decisions, setDecisions] = useState<Array<{ type: ApprovalType; scope: ApprovalScope }>>(
    pending.action_requests.map((action) => ({ type: defaultDecision(action), scope: "once" })),
  );
  const [answer, setAnswer] = useState("");
  const question = pending.kind === "ask_user" ? pending.question ?? null : null;

  useEffect(() => {
    setDecisions(pending.action_requests.map((action) => ({ type: defaultDecision(action), scope: "once" })));
    setAnswer("");
  }, [decisionSignature, pending.identity, pending.interrupt_id, pending.kind, pending.question?.prompt]);

  if (question) {
    return (
      <div className="approval-card" role="alertdialog" aria-labelledby="approval-title">
        <h3 id="approval-title">{answerTypeLabel(question)}</h3>
        <p>{question.prompt}</p>
        <p className="hint">This answers the assistant's question. It is not a permission grant and does not add file or folder authority.</p>
        {question.answer_type === "choice" ? (
          <fieldset className="choice-set">
            <legend>Choices</legend>
            {question.choices.map((choice) => (
              <label key={choice} className="check-row">
                <input type="radio" name="ask-user-choice" checked={answer === choice} onChange={() => setAnswer(choice)} />
                {choice}
              </label>
            ))}
          </fieldset>
        ) : (
          <label>
            {answerTypeLabel(question)}
            <input value={answer} onChange={(event) => setAnswer(event.target.value)} />
          </label>
        )}
        {question.answer_type === "file" || question.answer_type === "folder" ? (
          <NativePathSelector answerType={question.answer_type} busy={busy} onSelect={setAnswer} />
        ) : null}
        <div className="actions">
          <button type="button" disabled={busy || !answer.trim()} onClick={() => onRespond({ answer })}>
            Send answer
          </button>
          <button type="button" className="danger" disabled={busy} onClick={() => onRespond({ answer: "", cancelled: true })}>
            Cancel question
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="approval-card" role="alertdialog" aria-labelledby="approval-title">
      <h3 id="approval-title">Review requested actions</h3>
      <p className="notice notice-warn">
        Choose a decision for each action. Session and always grants apply only to matching future actions with the same recorded scope.
      </p>
      <ul className="plain-list">
        {pending.action_requests.map((action, index) => {
          const command = interruptCommand(action);
          const workingFolder = actionWorkingFolder(action);
          const decision = decisions[index] ?? { type: defaultDecision(action), scope: "once" as const };
          return (
            <li key={`${action.name}-${index}`} className="approval-action">
              <strong>{index + 1}. {actionTitle(action)}</strong>
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
              <fieldset className="choice-set">
                <legend>Decision for action {index + 1}</legend>
                {action.allowed_decisions.includes("approve") ? (
                  <>
                    <label className="check-row">
                      <input
                        type="radio"
                        name={`decision-${index}`}
                        checked={decision.type === "approve" && decision.scope === "once"}
                        onChange={() => setDecisions((current) => current.map((item, itemIndex) => itemIndex === index ? { type: "approve", scope: "once" } : item))}
                      />
                      Approve once
                    </label>
                    <label className="check-row">
                      <input
                        type="radio"
                        name={`decision-${index}`}
                        checked={decision.type === "approve" && decision.scope === "session"}
                        onChange={() => setDecisions((current) => current.map((item, itemIndex) => itemIndex === index ? { type: "approve", scope: "session" } : item))}
                      />
                      Allow for this session
                    </label>
                    <label className="check-row">
                      <input
                        type="radio"
                        name={`decision-${index}`}
                        checked={decision.type === "approve" && decision.scope === "always"}
                        onChange={() => setDecisions((current) => current.map((item, itemIndex) => itemIndex === index ? { type: "approve", scope: "always" } : item))}
                      />
                      Always allow
                    </label>
                  </>
                ) : null}
                {action.allowed_decisions.includes("reject") ? (
                  <label className="check-row">
                    <input
                      type="radio"
                      name={`decision-${index}`}
                      checked={decision.type === "reject"}
                      onChange={() => setDecisions((current) => current.map((item, itemIndex) => itemIndex === index ? { type: "reject", scope: "once" } : item))}
                    />
                    Reject
                  </label>
                ) : null}
              </fieldset>
            </li>
          );
        })}
      </ul>
      <div className="actions">
        <button
          type="button"
          disabled={busy || decisions.length !== pending.action_requests.length}
          onClick={() => onRespond({ decisions })}
        >
          Send decisions
        </button>
      </div>
    </div>
  );
}
