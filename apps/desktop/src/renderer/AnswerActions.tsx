import { CopyIconButton } from "./CopyIconButton";

export function AnswerActions({ answerText }: { answerText: string }) {
  return (
    <div className="answer-actions" role="group" aria-label="Answer actions">
      <CopyIconButton text={answerText} label="Copy answer" />
    </div>
  );
}
