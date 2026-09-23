import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";
import { MenuPopover } from "./MenuPopover";
import { CompactSlider } from "./CompactControls";
import { tokenLabel } from "./ModelControls";
import { Notice } from "./Notice";
import { HoverHelp } from "./HoverHelp";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { mergedStartup } from "./deploymentSettings";
import { errorMessage } from "./errors";
import { configurationLabel, findConfiguration } from "./configurationLabel";
import { useSetupPreview } from "./effectiveSettings";
import type { BundleConfigurationOptions, Deployment, RunProfile } from "./types";
import type { SetupConfiguration } from "./workspaceApi";
import "./ChatModelControls.css";

const modelFields = ["model_configuration_id", "deployment_id", "profile_id", "bundle_id", "inherit_deployment_settings", "startup_overrides", "per_request_overrides"] as const;
function modelSettings(configuration: SetupConfiguration): SetupConfiguration {
  return Object.fromEntries(modelFields.filter(key => Object.hasOwn(configuration, key)).map(key => [key, configuration[key]]));
}

export interface ChatModelControlsProps {
  deployments: Deployment[];
  profiles: RunProfile[];
  selectedDeploymentId: string;
  configuration: SetupConfiguration;
  projectId?: string | null;
  agentSetupVersionId?: string | null;
  conversationId?: string | null;
  disabled?: boolean;
  runtimeBusy?: boolean;
  onApply: (configuration: SetupConfiguration) => void | Promise<void>;
  onReloaded: () => Promise<void>;
}

export function ChatModelControls({ deployments, profiles, selectedDeploymentId, configuration, projectId = null, agentSetupVersionId = null, conversationId = null, disabled = false, runtimeBusy = false, onApply, onReloaded }: ChatModelControlsProps) {
  const [draft, setDraft] = useState(() => modelSettings(configuration));
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const incoming = JSON.stringify(modelSettings(configuration));
  const identity = `${conversationId}:${projectId}:${agentSetupVersionId}:${incoming}`;
  const currentOwner = useRef({ identity });
  if (currentOwner.current.identity !== identity) currentOwner.current = { identity };
  const owner = currentOwner.current;
  const latest = useRef({ configuration, onApply }); latest.current = { configuration, onApply };
  useEffect(() => { setDraft(JSON.parse(incoming) as SetupConfiguration); setError(""); setNotice(""); }, [incoming, conversationId]);
  const preview = useSetupPreview({ ...configuration, ...draft }, projectId, agentSetupVersionId);
  const resolved = preview.data?.configuration;
  const facts = preview.data?.effective_values ?? {};
  const selected = findConfiguration(profiles, resolved?.model_configuration_id ?? draft.model_configuration_id);
  const deployment = deployments.find(item => item.id === (resolved?.deployment_id ?? draft.deployment_id ?? selectedDeploymentId));
  const saveTarget = facts.model_configuration_target;
  const savedConfiguration = findConfiguration(profiles, typeof saveTarget?.value === "string" ? saveTarget.value : null);
  const bundleId = selected?.bundle_id ?? deployment?.bundle_id;
  const optionKey = `${bundleId}:${deployment?.id}`;
  const [optionsResult, setOptionsResult] = useState<{ key: string; data: BundleConfigurationOptions } | null>(null);
  useEffect(() => {
    if (!bundleId && !deployment?.id) return;
    let cancelled = false;
    const request = bundleId ? api.modelConfiguration(bundleId, deployment?.id) : api.deploymentConfiguration(deployment!.id);
    void request.then(data => { if (!cancelled) setOptionsResult({ key: optionKey, data }); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [optionKey, bundleId, deployment?.id]);
  const options = optionsResult?.key === optionKey ? optionsResult.data : null;
  const modelChoice = draft.model_configuration_id ? `configuration:${findConfiguration(profiles, draft.model_configuration_id)?.id ?? draft.model_configuration_id}` : draft.deployment_id && deployments.find(item => item.id === draft.deployment_id)?.scope === "connected" ? `deployment:${draft.deployment_id}` : "";
  const inheritedSource = !modelChoice ? facts.model_selection?.source : undefined;
  const automaticLabel = inheritedSource === "Loaded model" ? "Use loaded model" : inheritedSource?.startsWith("Project:") || inheritedSource?.startsWith("Agent:") ? `Use ${inheritedSource}` : inheritedSource?.startsWith("Application default") ? "Use app default" : "Use chat default";
  const modelName = configurationLabel(findConfiguration(profiles, configuration.model_configuration_id)) ?? deployments.find(item => item.id === selectedDeploymentId)?.display_name.replace(/^(managed|connected):/, "") ?? "Choose model";
  const loadedContext = deployment?.server_props?.n_ctx;
  const desiredContext = typeof draft.startup_overrides?.ctx_size === "number" ? draft.startup_overrides.ctx_size : typeof facts["startup.ctx_size"]?.value === "number" ? facts["startup.ctx_size"].value as number : loadedContext;
  const contextChoices = options?.context_size.options.flatMap(item => typeof item.value === "number" && item.value > 0 ? [item.value] : []) ?? [];
  const contextReason = runtimeBusy ? "Wait for this conversation’s running and queued work to finish." : deployment?.scope === "connected" ? "This server is managed outside Workbench. Change context in the app that runs it." : !deployment?.health?.healthy ? "Load the model to change its active context." : undefined;
  const reloadNeeded = deployment?.health?.healthy && Object.values(facts).some(item => item.requires_reload);
  const stageContext = (value: number) => setDraft(current => ({ ...current, startup_overrides: { ...current.startup_overrides, ctx_size: value } }));
  const startup = () => mergedStartup(selected?.bags.startup.requested ?? deployment?.requested_startup ?? deployment?.settings?.startup.requested ?? {}, draft.startup_overrides ?? {});
  async function act(operation: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try { await operation(); } catch (failure) { if (currentOwner.current === owner) setError(errorMessage(failure)); } finally { pending.current = false; setBusy(false); }
  }
  return <MenuPopover label={`Chat model settings: ${modelName}`} className="chat-model-controls" panelClassName="chat-model-controls-panel" trigger={<><Icon name="models" size={16} /><span className="chat-model-controls-model">{modelName}</span></>} disabled={disabled}>
    {close => <><div className="chat-model-controls-grid"><label>Model<select aria-label="Model" value={modelChoice} disabled={busy} onChange={event => {
      const choice = event.target.value;
      if (choice === modelChoice) return;
      setDraft(current => {
        const request = { ...current.per_request_overrides };
        for (const key of ["reasoning", "reasoning_effort", "reasoning_format"]) delete request[key];
        return { ...current, model_configuration_id: choice.startsWith("configuration:") ? choice.slice(14) : null, deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null, profile_id: null, bundle_id: null, inherit_deployment_settings: null, per_request_overrides: request, startup_overrides: {} };
      });
    }}><option value="">{automaticLabel}</option>{profiles.filter(item => item.bundle_id).map(item => <option key={item.id} value={`configuration:${item.id}`}>{configurationLabel(item)}</option>)}{deployments.filter(item => item.scope === "connected").map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name} · connected</option>)}</select></label></div>
      {!modelChoice && typeof facts.model_selection?.value === "string" ? <span className="hint">{facts.model_selection.value} · {facts.model_selection.source}</span> : null}
      <div className="chat-context-control"><div className="setting-title"><span>Context {loadedContext ? `${tokenLabel(loadedContext)} loaded` : "not reported"}</span><HoverHelp title="Context">Larger context uses more memory. Apply reloads an idle managed model and preserves this conversation. Running work and other consumers can block a reload.</HoverHelp></div>
        {desiredContext ? <><CompactSlider label="Context size" value={desiredContext} values={contextChoices} formatValue={tokenLabel} onChange={stageContext} disabled={busy || !!contextReason} /><input aria-label="Exact context size" type="number" min={1} max={options?.context_size.maximum ?? undefined} value={desiredContext} disabled={busy || !!contextReason} onChange={event => { const value = Number(event.target.value); if (value > 0) stageContext(value); }} /></> : null}
        {contextReason ? <span className="hint">{contextReason}</span> : null}
      </div>
      <ResponseSettingsEditor compact value={draft.per_request_overrides ?? {}} onChange={per_request_overrides => setDraft(current => ({ ...current, per_request_overrides }))} options={options} facts={facts} disabled={busy || preview.loading} />
      {error || preview.error ? <Notice tone="error">{error || preview.error}</Notice> : null}{notice ? <Notice tone="info">{notice}</Notice> : null}
      <div className="actions"><button type="button" className="primary-button" disabled={busy || preview.loading || !!preview.error || Boolean(reloadNeeded && contextReason)} onClick={() => void act(async () => {
        if (reloadNeeded && deployment) {
          try {
            const next = await api.reconfigure(deployment.id, { startup: startup(), replace_startup: true, ...(selected && selected.id !== deployment.profile_id ? { model_configuration_id: selected.id, expected_configuration_revision: selected.revision } : {}), expected_updated_at: deployment.updated_at, conversation_id: conversationId });
            if (!next.health?.healthy) throw new Error(next.error ?? "Model did not become ready.");
          } catch (failure) {
            await onReloaded().catch(() => {});
            throw failure;
          }
          await onReloaded();
        }
        if (currentOwner.current !== owner) return;
        await latest.current.onApply({ ...latest.current.configuration, ...draft });
        if (currentOwner.current === owner) close();
      })}>{busy ? "Applying…" : reloadNeeded ? "Apply & reload" : "Apply"}</button>
      <button type="button" disabled={busy || preview.loading || !!preview.error || !savedConfiguration?.bundle_id} title={!savedConfiguration ? saveTarget?.unavailable_reason ?? "Choose a saved model configuration first" : `Save to ${saveTarget.source} for future work`} onClick={() => void act(async () => {
        if (!savedConfiguration?.bundle_id) return;
        await api.saveModelConfiguration(savedConfiguration.bundle_id, { display_name: savedConfiguration.display_name, configuration_id: savedConfiguration.id, expected_revision: savedConfiguration.revision, startup: startup(), per_request: mergedStartup(selected?.bags.per_request.requested ?? deployment?.settings.per_request.requested ?? {}, draft.per_request_overrides ?? {}) });
        await onReloaded(); if (currentOwner.current === owner) setNotice("Saved to model. Apply separately to use these chat changes.");
      })}>Save to model</button></div>
    </>}
  </MenuPopover>;
}
