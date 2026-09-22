import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export async function pickWorkbenchPath(kind: "file" | "folder"): Promise<string | null> {
  const selected = await window.workbench?.selectPath?.(kind);
  return selected || null;
}

export function PathBrowseButton(props: {
  kind: "file" | "folder";
  label: string;
  icon?: IconName;
  disabled?: boolean;
  onPicked: (path: string) => void;
  onError?: (error: unknown) => void;
}) {
  return (
    <button
      type="button"
      disabled={props.disabled || !window.workbench?.selectPath}
      onClick={() => {
        void pickWorkbenchPath(props.kind).then(path => { if (path) props.onPicked(path); }).catch(error => props.onError?.(error));
      }}
    >
      {props.icon ? <><Icon name={props.icon} size={15} /> </> : null}{props.label}
    </button>
  );
}

export function PathField(props: {
  kind: "file" | "folder";
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  required?: boolean;
  buttonLabel: string;
  icon?: IconName;
  onPicked?: (path: string) => void;
  onError?: (error: unknown) => void;
}) {
  return (
    <>
      <label>
        {props.label}
        <input required={props.required} value={props.value} disabled={props.disabled} placeholder={props.placeholder} onChange={event => props.onChange(event.target.value)} />
      </label>
      <PathBrowseButton
        kind={props.kind}
        label={props.buttonLabel}
        icon={props.icon}
        disabled={props.disabled}
        onError={props.onError}
        onPicked={path => {
          props.onChange(path);
          props.onPicked?.(path);
        }}
      />
    </>
  );
}
