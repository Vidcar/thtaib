type ScaffoldSurface = "scaffold";

function surfaceLabel(surface: ScaffoldSurface): string {
  switch (surface) {
    case "scaffold":
      return "Windows-first scaffold";
    default: {
      const unexpected: never = surface;
      return unexpected;
    }
  }
}

export function App() {
  const productName = window.workbench?.productName ?? "Local AI Workbench";
  const surface: ScaffoldSurface = window.workbench?.surface ?? "scaffold";

  return (
    <main className="shell">
      <p className="eyebrow">Local AI Workbench</p>
      <h1>{productName}</h1>
      <p className="lede">
        {surfaceLabel(surface)}. Chat, Lab, and Builder are not part of this
        milestone.
      </p>
      <dl className="meta">
        <div>
          <dt>Layout</dt>
          <dd>apps/backend · apps/desktop</dd>
        </div>
        <div>
          <dt>Question</dt>
          <dd>OQ-001</dd>
        </div>
      </dl>
    </main>
  );
}
