import { useEffect, useRef, useState, type ReactNode } from "react";

import type { AppearanceToken } from "./appearanceValue";
import { Icon } from "./Icon";

export function AppearancePreview({ active }: { active: AppearanceToken | null }) {
  const [guides, setGuides] = useState(true);
  const frameRef = useRef<HTMLDivElement>(null);
  const aimed = active?.id ?? "";

  useEffect(() => {
    const marked = frameRef.current?.querySelector(".is-hit");
    marked?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [aimed]);

  return (
    <aside className={`appearance-stage${guides ? " show-guides" : ""}`} data-active={aimed} aria-label="Appearance preview">
      <div className="appearance-stage-bar">
        <strong>Preview</strong>
        <label>
          <input type="checkbox" data-appearance-guide="" checked={guides} onChange={event => setGuides(event.target.checked)} />
          Spacing guides
        </label>
      </div>
      <p className="appearance-stage-caption">
        {active ? `${active.name}. ${active.detail}` : "Point at a control. The marked parts are what it changes."}
      </p>
      <div className="appearance-stage-frame" ref={frameRef}>
        <div className="appearance-stage-scene" aria-hidden="true">
          <Hit active={aimed} guide tokens={["palette-bg-nav", "layout-side", "space-section", "pad-compact", "palette-border", "line-hairline", "font-ui"]} className="appearance-stage-side">
            <Hit active={aimed} tokens={["text-body", "weight-semibold"]} className="appearance-stage-brand">Workbench</Hit>
            <Hit active={aimed} tokens={["space-compact"]} className="appearance-stage-nav">
              <Hit active={aimed} guide tokens={["text-body", "weight-regular", "radius-control", "pad-tight", "control-height", "palette-text", "icon-md", "icon-stroke"]} className="appearance-stage-item">
                <Icon name="chat" size={16} /> Chat
              </Hit>
              <Hit active={aimed} tokens={["palette-hover", "radius-control"]} className="appearance-stage-item is-hover">Models</Hit>
              <Hit active={aimed} tokens={["text-small", "palette-muted", "tracking-wide", "weight-medium"]} className="appearance-stage-kicker">Today</Hit>
              <Hit active={aimed} tokens={["palette-bg-raised", "tint-quiet", "tint-strong", "focus-ring", "focus-offset", "palette-accent"]} className="appearance-stage-item is-current">Appearance</Hit>
            </Hit>
            <Hit active={aimed} tokens={["space-tight"]} className="appearance-stage-icons">
              <Hit active={aimed} tokens={["icon-lg", "icon-stroke"]}><Icon name="info" size={20} /></Hit>
              <Hit active={aimed} tokens={["icon-xl", "icon-stroke"]}><Icon name="sparkles" size={28} /></Hit>
            </Hit>
          </Hit>
          <Hit active={aimed} guide tokens={["palette-bg", "pad-page", "layout-inset", "space-section", "layout-page", "font-ui"]} className="appearance-stage-main">
            <Hit active={aimed} tokens={["text-heading", "weight-semibold"]} className="appearance-stage-title">Page title</Hit>
            <Hit active={aimed} tokens={["text-title", "weight-medium"]} className="appearance-stage-hero">What are we working on?</Hit>
            <Hit active={aimed} tokens={["layout-reading", "space-stack"]} className="appearance-stage-column">
              <Hit active={aimed} guide tokens={["palette-bg-raised", "radius-composer", "pad-card", "layout-message", "shadow-soft", "text-ui"]} className="appearance-stage-bubble">Your message</Hit>
              <Hit active={aimed} tokens={["text-ui", "leading-body", "palette-text"]} className="appearance-stage-answer">
                Answer text stays readable on its own. <Hit active={aimed} tokens={["tint-soft"]} className="appearance-stage-selection">Selected</Hit> words use the soft tint.
              </Hit>
              <Hit active={aimed} tokens={["text-small", "palette-muted", "line-strong", "palette-border"]} className="appearance-stage-reasoning">Reasoning stays quieter than the answer.</Hit>
              <Hit active={aimed} tokens={["text-small", "fade-quiet", "palette-muted"]} className="appearance-stage-hint">Hint</Hit>
              <Hit active={aimed} tokens={["font-mono", "font-code", "text-small"]} className="appearance-stage-code">const notes = true</Hit>
              <Hit active={aimed} tokens={["font-editor", "font-mono", "palette-bg-input"]} className="appearance-stage-editor">editor.ts</Hit>
              <Hit active={aimed} tokens={["space-compact"]} className="appearance-stage-cards">
                <Hit active={aimed} guide tokens={["palette-bg-panel", "radius-card", "pad-card", "line-hairline", "layout-panel", "shadow-soft", "weight-medium", "text-body"]} className="appearance-stage-card">Card</Hit>
                <Hit active={aimed} guide tokens={["pad-section", "radius-card", "palette-bg-panel", "line-hairline"]} className="appearance-stage-card">Section</Hit>
              </Hit>
              <Hit active={aimed} tokens={["palette-warn", "tint-quiet", "tint-half", "tint-strong", "palette-bg-panel", "radius-card", "text-body"]} className="appearance-stage-warn">Approval needs a decision.</Hit>
              <Hit active={aimed} tokens={["space-tight"]} className="appearance-stage-actions">
                <Hit active={aimed} guide tokens={["pad-tight", "pad-compact", "radius-control", "control-height", "line-hairline", "palette-border", "text-body"]} className="appearance-stage-button">Keep</Hit>
                <Hit active={aimed} tokens={["fade-disabled", "radius-control"]} className="appearance-stage-button is-off">Disabled</Hit>
                <Hit active={aimed} tokens={["palette-danger", "tint-half", "radius-control"]} className="appearance-stage-button is-danger">Remove</Hit>
                <Hit active={aimed} tokens={["palette-live", "radius-pill", "text-small", "leading-tight"]} className="appearance-stage-badge">Live</Hit>
                <Hit active={aimed} tokens={["palette-ok", "radius-pill", "text-small"]} className="appearance-stage-badge is-ok">Saved</Hit>
              </Hit>
              <Hit active={aimed} tokens={["palette-bg-input", "radius-control", "pad-compact", "text-ui", "layout-column"]} className="appearance-stage-field">Field</Hit>
              <Hit active={aimed} guide tokens={["palette-bg-raised", "radius-composer", "pad-card", "shadow-soft", "space-tight"]} className="appearance-stage-composer">
                <span>Composer</span>
                <Hit active={aimed} tokens={["palette-accent", "radius-circle", "control-height-lg", "weight-bold"]} className="appearance-stage-send">Send</Hit>
              </Hit>
              <Hit active={aimed} tokens={["layout-narrow", "layout-menu", "text-small"]} className="appearance-stage-menu">
                <span>One</span><span>Two</span><span>Three</span><span>Four</span><span>Five</span>
              </Hit>
              <Hit active={aimed} tokens={["layout-dialog"]} className="appearance-stage-pop">
                <span className="appearance-stage-behind">Notes behind the dialog</span>
                <Hit active={aimed} tokens={["palette-scrim"]} className="appearance-stage-scrim" />
                <Hit active={aimed} tokens={["effect-blur", "palette-shadow", "pad-card", "text-body"]} className="appearance-stage-dialog">Dialog</Hit>
              </Hit>
            </Hit>
          </Hit>
        </div>
      </div>
    </aside>
  );
}

function Hit({ active, tokens, className, children, guide }: { active: string; tokens: string[]; className?: string; children?: ReactNode; guide?: boolean }) {
  const marked = active !== "" && tokens.includes(active);
  return (
    <div className={`${className ?? ""}${marked ? " is-hit" : ""}`} data-guide={guide ? "" : undefined}>
      {children}
    </div>
  );
}
