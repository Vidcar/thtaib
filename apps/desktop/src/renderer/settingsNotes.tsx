export type RetiredNote = {
  key: string;
  requested: unknown;
  applied: unknown;
  reason: string;
};

export type StartupMismatch = {
  key: string;
  selected: unknown;
  loaded: unknown;
};

export function SettingsNotes({
  unsupported,
  retired,
}: {
  unsupported?: string[];
  retired?: RetiredNote[];
}) {
  const hasUnsupported = Boolean(unsupported?.length);
  const hasRetired = Boolean(retired?.length);
  if (!hasUnsupported && !hasRetired) {
    return null;
  }
  return (
    <div className="settings-notes">
      {hasUnsupported ? (
        <p className="notice notice-warn">
          Unsupported startup: {unsupported?.join(", ")}
        </p>
      ) : null}
      {hasRetired
        ? retired?.map((note) => (
            <p key={note.key} className="notice notice-warn">
              Retired {note.key}: {note.reason}
            </p>
          ))
        : null}
    </div>
  );
}

export function EffectiveSetupNotes({
  unsupportedStartup,
  retiredStartup,
  startupMismatches,
  gaps,
}: {
  unsupportedStartup?: string[];
  retiredStartup?: RetiredNote[];
  startupMismatches?: StartupMismatch[];
  gaps?: string[];
}) {
  return (
    <div className="settings-notes">
      <SettingsNotes unsupported={unsupportedStartup} retired={retiredStartup} />
      {startupMismatches?.length ? (
        <p className="notice notice-warn">
          Startup mismatches:{" "}
          {startupMismatches
            .map((item) => `${item.key}: selected ${String(item.selected)} / loaded ${String(item.loaded)}`)
            .join(" · ")}
        </p>
      ) : null}
      {gaps?.length ? <p className="notice notice-info">Gaps: {gaps.join(" · ")}</p> : null}
    </div>
  );
}
