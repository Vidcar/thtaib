import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

export function CopyIconButton({ text, label }: { text: string; label: string }) {
  const [copyState, setCopyState] = useState<"ready" | "copied" | "failed">("ready");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (resetTimer.current) clearTimeout(resetTimer.current); }, []);
  const accessible = copyState === "copied" ? "Copied" : copyState === "failed" ? "Retry copy" : label;
  return (
    <button
      type="button"
      className="copy-code icon-button"
      aria-label={accessible}
      title={accessible}
      disabled={copyState === "copied"}
      onClick={() => {
        if (!text || !navigator.clipboard) { setCopyState("failed"); return; }
        void navigator.clipboard.writeText(text).then(() => {
          setCopyState("copied");
          if (resetTimer.current) clearTimeout(resetTimer.current);
          resetTimer.current = setTimeout(() => setCopyState("ready"), 2000);
        }).catch(() => setCopyState("failed"));
      }}
    >
      <Icon name={copyState === "copied" ? "check" : "copy"} size={14} />
    </button>
  );
}
