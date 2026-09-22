import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import { packet03Api, type RetainedAsset } from "./packet03Api";
import { loadRetainedPreview } from "./retainedFiles";
import "./ImagePreview.css";

export function safeImageDataUrl(value: unknown): string | undefined {
  return typeof value === "string" && value.length <= 12_000_000 && /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value) ? value : undefined;
}

export function ImagePreview({ src, name, loadOriginal, small = false }: {
  src: string; name: string; loadOriginal?: () => Promise<string>; small?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [original, setOriginal] = useState<string>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const generation = useRef(0);
  useEffect(() => { setOriginal(undefined); return () => { generation.current += 1; }; }, [src]);
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  const safeSrc = safeImageDataUrl(src);
  if (!safeSrc) return <span>Image unavailable</span>;
  function close() {
    generation.current += 1;
    dialog.current?.close();
    setOpen(false); setLoading(false);
    trigger.current?.focus();
  }
  async function expand() {
    setOpen(true); setError(""); setZoomed(false);
    if (!loadOriginal || original) return;
    const request = ++generation.current;
    setLoading(true);
    try {
      const next = safeImageDataUrl(await loadOriginal());
      if (!next) throw new Error("This image could not be displayed.");
      if (generation.current === request) setOriginal(next);
    } catch (caught) {
      if (generation.current === request) setError(caught instanceof Error ? caught.message : String(caught));
    } finally { if (generation.current === request) setLoading(false); }
  }
  return <>
    <button ref={trigger} type="button" className={`image-preview-button${small ? " is-small" : ""}`} aria-label={`View image ${name}`} onClick={() => void expand()}>
      <img src={safeSrc} alt={name} loading="lazy" /><span><Icon name="expand" size={13} /> View</span>
    </button>
    {open && createPortal(<dialog ref={dialog} className="image-viewer" aria-label={name} onCancel={event => { event.preventDefault(); close(); }} onClose={close} onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <header><strong>{name}</strong><button type="button" onClick={() => setZoomed(value => !value)}>{zoomed ? "Fit image" : "Actual size"}</button><button type="button" className="icon-button" aria-label="Close image" onClick={close}><Icon name="close" /></button></header>
      {loading ? <p role="status">Loading full image…</p> : null}{error ? <p role="alert">{error}</p> : null}
      <div className={`image-viewer-canvas${zoomed ? " is-zoomed" : ""}`}><img src={original ?? safeSrc} alt={name} /></div>
    </dialog>, document.body)}
  </>;
}

export function RetainedImage({ asset, sessionId, small = false }: { asset: RetainedAsset; sessionId?: string; small?: boolean }) {
  const [preview, setPreview] = useState<string>();
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const scope = { sessionId: sessionId ?? asset.session_id, projectPath: asset.project_path ?? undefined };
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") { setVisible(true); return; }
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect(); } }, { rootMargin: "160px" });
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let stale = false;
    setPreview(undefined); setError("");
    void loadRetainedPreview(asset.id, scope).then(result => {
      if (!stale) setPreview(result.image_data_url ?? undefined);
    }).catch(caught => { if (!stale) setError(caught instanceof Error ? caught.message : String(caught)); });
    return () => { stale = true; };
  }, [visible, asset.id, scope.sessionId, scope.projectPath]);
  return <div className={`retained-image${small ? " is-small" : ""}`} ref={container}>
    {preview ? <ImagePreview src={preview} name={asset.filename} small={small} loadOriginal={async () => {
      const content = await packet03Api.contentAsset(asset.id, scope);
      return `data:${content.content_type};base64,${content.content_base64 ?? ""}`;
    }} /> : <span className="hint" role={error ? "status" : undefined}>{error || "Image"}</span>}
  </div>;
}
