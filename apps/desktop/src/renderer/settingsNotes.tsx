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

function retiredText(notes: RetiredNote[] | undefined): string {
  if (!notes?.length) {
    return "none";
  }
  return notes.map((note) => `${note.key}: ${note.reason}`).join(" | ");
}

export function SettingsNotes({
  unsupported,
  retired,
}: {
  unsupported?: string[];
  retired?: RetiredNote[];
}) {
  return (
    <>
      <p>unsupported startup: {unsupported?.length ? unsupported.join(", ") : "none"}</p>
      <p>retired startup: {retiredText(retired)}</p>
    </>
  );
}

export function EffectiveSetupNotes({
  unsupportedStartup,
  retiredStartup,
  startupMismatches,
}: {
  unsupportedStartup?: string[];
  retiredStartup?: RetiredNote[];
  startupMismatches?: StartupMismatch[];
}) {
  return (
    <div>
      <SettingsNotes unsupported={unsupportedStartup} retired={retiredStartup} />
      <p>
        startup mismatches:{" "}
        {startupMismatches?.length
          ? startupMismatches
              .map((item) => `${item.key}: selected ${String(item.selected)} / loaded ${String(item.loaded)}`)
              .join(" | ")
          : "none"}
      </p>
    </div>
  );
}