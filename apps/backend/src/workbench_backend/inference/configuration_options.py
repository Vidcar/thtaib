"""Computed runtime controls for a bundle.

These descriptors are UI-facing data derived from GGUF metadata, Workbench
startup defaults and optional observed llama-server properties. They do not
rewrite profiles or infer capabilities.
"""

from __future__ import annotations

import re
import json

from typing import Any

import psutil
from jinja2 import Environment, TemplateSyntaxError, nodes
from workbench_backend.errors import HarnessError

from workbench_backend.inference.schemas import (
    BundleConfigurationOptions,
    Deployment,
    GgufRuntimeMetadata,
    HuggingFaceConfiguration,
    RuntimeControlDescriptor,
    RuntimeControlOption,
    ResponseRecipe,
    ResponsePreset,
    SettingsBag,
)
from workbench_backend.inference.settings import (
    DEFAULT_GPU_PROFILE, NATIVE_REQUEST_DEFAULTS, NATIVE_STARTUP_DEFAULTS,
    STARTUP_ENUMS, STARTUP_KEYS, PER_REQUEST_KEYS,
    REQUEST_STARTUP_ALIASES, control_facts, normalize_per_request_requested,
)

SMALL_CONTEXT_VALUES = (1024, 2048, 4096, 8192, 16384)
MIN_LARGE_CONTEXT_OPTION = 32 * 1024
CONTEXT_FRACTIONS = (1 / 8, 3 / 16, 1 / 4, 3 / 8, 1 / 2, 5 / 8, 3 / 4, 1)


def bundle_configuration_options(
    bundle_id: str | None,
    metadata: GgufRuntimeMetadata,
    *,
    deployment: Deployment | None = None,
    recommended_threads: int | None = None,
    huggingface_configuration: HuggingFaceConfiguration | None = None,
    selected_template_source: str | None = None,
) -> BundleConfigurationOptions:
    """Build controls from read-only bundle metadata and optional live props."""

    observed_context = (
        deployment.server_props.n_ctx
        if deployment is not None and deployment.server_props is not None
        else None
    )
    per_request_defaults = {**_request_catalogue(native_defaults=bundle_id is not None), **_per_request_defaults(metadata, deployment,
        selected_template_source=selected_template_source)}
    selected_source = selected_template_source or (f"{huggingface_configuration.template_origin}_template"
        if huggingface_configuration and huggingface_configuration.template_file else None)
    if selected_source:
        for descriptor in per_request_defaults.values():
            if descriptor.source == "gguf_template":
                descriptor.source = selected_source
            if descriptor.default_source == "gguf_template":
                descriptor.default_source = selected_source
    if huggingface_configuration is not None:
        source = (f"Hugging Face {huggingface_configuration.source_repo_id}"
            if huggingface_configuration.source_verified else "Hugging Face GGUF repository")
        for key, value in huggingface_configuration.generation_defaults.items():
            if key == "max_tokens":
                continue
            observed = per_request_defaults.get(key)
            if observed is not None:
                # A publisher default is not evidence that the selected template
                # accepts a control or a new effort level.
                per_request_defaults[key] = observed.model_copy(update={
                    "default_value": value, "default_source": source,
                })
            else:
                per_request_defaults[key] = RuntimeControlDescriptor(
                    key=key, label=key.replace("_", " ").title(),
                    description="Downloaded generation setting used when no explicit override is saved.",
                    source="huggingface_generation_config", applied=value,
                    default_value=value, default_source=source,
                    supported=True,
                )
        recipe = preferred_response_recipe(metadata, huggingface_configuration, deployment=deployment)
        if recipe is not None:
            values = {key: value for key, value in recipe.per_request.items() if key != "max_tokens"}
            if recipe.reasoning != "preserve":
                values["reasoning"] = recipe.reasoning
            source = f"Model card {recipe.source_repo_id} · {recipe.name}"
            for key, value in values.items():
                descriptor = per_request_defaults.get(key)
                if descriptor is not None:
                    per_request_defaults[key] = descriptor.model_copy(update={
                        "applied": value, "default_value": value, "default_source": source,
                    })
    startup_defaults = {**_startup_catalogue(), **_startup_defaults(recommended_threads=recommended_threads),
        **_speculative_descriptors(metadata)}
    history = reasoning_history_descriptor(metadata, deployment)
    if selected_source and history.source == "gguf_template":
        history.source = selected_source
        if history.default_source == "gguf_template":
            history.default_source = selected_source
    per_request_defaults["reasoning_preserve"] = history
    # Preserve the descriptor alias for reading old saved configurations. Its
    # shared timing still tells every editor that this is a request choice.
    startup_defaults["reasoning_preserve"] = history
    for key, descriptor in startup_defaults.items():
        updates = control_facts(key, per_request=key in REQUEST_STARTUP_ALIASES)
        if descriptor.default_value is None and descriptor.applied is not None:
            updates.update(default_value=descriptor.applied, default_source=descriptor.source)
        descriptor = descriptor.model_copy(update=updates)
        startup_defaults[key] = descriptor
    for key, descriptor in per_request_defaults.items():
        facts = control_facts(key, per_request=True)
        if descriptor.maximum is not None:
            facts.pop("maximum", None)
        facts["applied"] = descriptor.default_value
        per_request_defaults[key] = descriptor.model_copy(update=facts)
    context = _context_descriptor(metadata.context_length, observed_context)
    context_facts = control_facts("ctx_size")
    context_facts.pop("minimum", None)
    return BundleConfigurationOptions(
        bundle_id=bundle_id,
        deployment_id=deployment.id if deployment is not None else None,
        context_size=context.model_copy(update=context_facts),
        gpu_layers=_gpu_layers_descriptor(metadata.block_count).model_copy(update=control_facts("n_gpu_layers")),
        startup_defaults=startup_defaults,
        per_request_defaults=per_request_defaults,
        response_presets=response_presets(per_request_defaults),
        metadata={
            "architecture": metadata.architecture,
            "name": metadata.name,
            "context_length": metadata.context_length,
            "block_count": metadata.block_count,
            "nextn_predict_layers": metadata.nextn_predict_layers,
            "has_mtp_tensors": metadata.has_mtp_tensors,
        },
    )


def _per_request_defaults(metadata: GgufRuntimeMetadata, deployment: Deployment | None, *, selected_template_source: str | None = None) -> dict[str, RuntimeControlDescriptor]:
    props = deployment.server_props if deployment is not None else None
    template = props.chat_template if props is not None and props.chat_template else metadata.chat_template or ""
    template = re.sub(r"\{#.*?#\}", "", template, flags=re.DOTALL)
    if selected_template_source is None and deployment is not None and not (props and props.chat_template) and any(
        deployment.applied_startup.get(key) for key in ("chat_template", "chat_template_file")
    ):
        template = ""
    source = "server_template" if props is not None and props.chat_template else "gguf_template"
    # Extract literal constraints from the selected template. A runtime accepting
    # an enum does not mean that a template understands or accepts its values.
    literals, accepted, closed = _template_efforts(template)
    efforts = [value for value in _ordered_reasoning_efforts(literals) if value != "default" and value in literals]
    known_unsupported = bool(props is not None and props.chat_template_caps.get("supports_reasoning_effort") is False)
    if known_unsupported:
        efforts = []
    elif template and _template_uses(template, "reasoning_effort") is False and _template_uses(template, "reasoning_strength") is False:
        known_unsupported = True
    thinking_toggle = _template_uses(template, "enable_thinking")
    effort_default = _literal_template_default(template, "reasoning_effort")
    # Native properties are authoritative after loading. Before loading, a
    # literal template default is useful guidance, not an observed probe result.
    thinking_default = props.chat_template_caps.get("supports_thinking") if props is not None else None
    thinking_default = thinking_default if isinstance(thinking_default, bool) else _template_boolean_default(template, "enable_thinking")
    defaults = {
        "reasoning_effort": RuntimeControlDescriptor(
            key="reasoning_effort",
            label="Thinking effort",
            description=(
                "Levels declared by this model's chat template."
                if efforts else "This model's template does not declare adjustable thinking levels."
            ),
            source=source if efforts else "unavailable",
            supported=True if efforts else False if known_unsupported else None,
            accepted_values=[] if known_unsupported else sorted(accepted) if closed else None,
            applied=effort_default if effort_default is not None else "default",
            default_value=effort_default if not known_unsupported else None,
            default_source=source if effort_default is not None and not known_unsupported else None,
            options=[
                RuntimeControlOption(
                    value=value,
                    label="Model default" if value == "default" else _title_effort(value),
                    description=(
                        "Leave reasoning effort to the model or profile default."
                        if value == "default"
                        else f"Send reasoning_effort={value} with this Chat request."
                    ),
                )
                for value in ([*efforts] if effort_default is not None else ["default", *efforts]) if efforts
            ],
        ),
        "reasoning": RuntimeControlDescriptor(
            key="reasoning", label="Thinking", description="Enable or disable thinking for this model's template.",
            source=source if thinking_toggle else "unavailable", supported=thinking_toggle if template else None,
            applied=("on" if thinking_default else "off") if isinstance(thinking_default, bool) else "auto",
            default_value=("on" if thinking_default else "off") if isinstance(thinking_default, bool) else None,
            default_source=("server_properties" if props and isinstance(props.chat_template_caps.get("supports_thinking"), bool)
                            else source) if isinstance(thinking_default, bool) else None,
            options=[RuntimeControlOption(value=value, label=label) for value, label in
                     ([('on', 'On'), ('off', 'Off')] if isinstance(thinking_default, bool) else
                      [('auto', 'Auto'), ('on', 'On'), ('off', 'Off')]) if thinking_toggle],
        ),
    }
    if props is not None:
        params = props.default_generation_settings.get("params", {})
        if isinstance(params, dict):
            for key in ("temperature", "top_k", "top_p", "min_p", "repeat_penalty", "presence_penalty", "frequency_penalty"):
                value = params.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    defaults[key] = RuntimeControlDescriptor(key=key, label=key.replace("_", " ").title(),
                        description="Default reported by the loaded model server.", source="server_properties",
                        observed=value, default_value=value, default_source="server_properties")
    if deployment is not None:
        kwargs = deployment.applied_startup.get("chat_template_kwargs")
        if isinstance(kwargs, str):
            try:
                kwargs = json.loads(kwargs)
            except ValueError:
                kwargs = None
        if isinstance(kwargs, dict):
            if isinstance(kwargs.get("enable_thinking"), bool):
                defaults["reasoning"].default_value = "on" if kwargs["enable_thinking"] else "off"
                defaults["reasoning"].default_source = "loaded_template_settings"
            if isinstance(kwargs.get("reasoning_effort"), str):
                defaults["reasoning_effort"].default_value = kwargs["reasoning_effort"]
                defaults["reasoning_effort"].default_source = "loaded_template_settings"
        for key in ("reasoning", "reasoning_effort"):
            value = deployment.applied_startup.get(key)
            if value is not None and value not in ("default", "auto"):
                defaults[key].default_value = value
                defaults[key].default_source = "loaded_startup"
    defaults["reasoning_budget_tokens"] = reasoning_budget_descriptor(deployment, metadata)
    return defaults


def _request_catalogue(*, native_defaults: bool) -> dict[str, RuntimeControlDescriptor]:
    native = NATIVE_REQUEST_DEFAULTS if native_defaults else {"max_tokens": -1}
    result = {}
    for key in sorted(PER_REQUEST_KEYS):
        value = native.get(key)
        result[key] = RuntimeControlDescriptor(
            key=key, label="Maximum output tokens" if key == "max_tokens" else key.replace("_", " ").title(),
            description=("Maximum generated tokens for thinking and the answer together. Unlimited uses native -1; Deep Agents manages context using the full loaded capacity."
                         if key == "max_tokens" else "Saved response setting, applied to the next accepted request."),
            source="pinned_runtime_default" if key in native else "pinned_runtime_schema",
            default_value=value, default_source="pinned_runtime_default" if key in native else None,
            supported=None if key.startswith("reasoning") else True,
            options=[RuntimeControlOption(value=-1, label="Unlimited")] if key == "max_tokens" else [],
        )
    result["reasoning_format"].options = [RuntimeControlOption(value=value, label=value.replace("-", " ").title())
                                         for value in sorted(STARTUP_ENUMS["reasoning_format"])]
    return result


def _startup_catalogue() -> dict[str, RuntimeControlDescriptor]:
    native = NATIVE_STARTUP_DEFAULTS
    return {key: RuntimeControlDescriptor(
        key=key, flag=flag, label=key.replace("_", " ").title(),
        description=("Auto uses four request slots with unified KV; simultaneous requests share the context pool."
                     if key == "parallel" else
                     "Share context across request slots. Native parallel Auto enables this; select an explicit request count to disable it."
                     if key == "kv_unified" else "Saved loading setting; a resident model requires a deliberate reload."),
        source="pinned_runtime_default" if key in native else "pinned_runtime_schema",
        applied=native.get(key), default_value=native.get(key), default_source="pinned_runtime_default" if key in native else None, supported=True,
        options=([RuntimeControlOption(value=-1, label="Auto")] if key in {
            "parallel", "threads", "threads_batch", "spec_draft_threads", "spec_draft_threads_batch"} else [])
            + [RuntimeControlOption(value=value, label=value.replace("-", " ").title())
                 for value in sorted(STARTUP_ENUMS.get(key, ()))],
    ) for key, flag in STARTUP_KEYS.items() if key not in REQUEST_STARTUP_ALIASES and key not in {"host", "port", "alias"}}


def preferred_response_recipe(
    metadata: GgufRuntimeMetadata, config: HuggingFaceConfiguration | None,
    *, deployment: Deployment | None = None,
) -> ResponseRecipe | None:
    """Choose only one compatible recommendation matching the template default."""
    if config is None:
        return None
    descriptors = _per_request_defaults(metadata, deployment)
    mode = descriptors["reasoning"].default_value
    candidates = []
    for recipe in config.response_recipes:
        if recipe.reasoning != "preserve" and (descriptors["reasoning"].supported is not True or recipe.reasoning != mode):
            continue
        _, invalid = normalize_per_request_requested(recipe.per_request)
        if invalid:
            continue
        effort = recipe.per_request.get("reasoning_effort")
        descriptor = descriptors["reasoning_effort"]
        if effort not in {None, "default", "none"} and (
            descriptor.supported is not True or descriptor.accepted_values is not None and effort not in descriptor.accepted_values
        ):
            continue
        candidates.append(recipe)
    return candidates[0] if len(candidates) == 1 else None


def response_default_values(options: BundleConfigurationOptions) -> dict[str, Any]:
    """Canonical inherited baseline; viewing it never creates overrides."""
    return {key: descriptor.default_value for key, descriptor in options.per_request_defaults.items()
            if descriptor.default_value is not None and descriptor.supported is not False}


def _literal_template_default(template: str, variable: str):
    """Read explicit literal defaults only; never evaluate untrusted templates."""
    matches = re.findall(r"\b" + re.escape(variable) + r"\s*\|\s*default\s*\(\s*(['\"][a-z]+['\"]|true|false)\s*\)", template)
    values = {True if value == "true" else False if value == "false" else value[1:-1] for value in matches}
    return next(iter(values)) if len(values) == 1 else None


def _template_boolean_default(template: str, variable: str) -> bool | None:
    literal = _literal_template_default(template, variable)
    if isinstance(literal, bool):
        return literal
    name = re.escape(variable)
    if re.search(r"\b" + name + r"\s+is\s+undefined\s+or\s+" + name + r"\s+is\s+true\b", template):
        return True
    if re.search(r"\b" + name + r"\s+is\s+defined\s+and\s+" + name + r"\s+is\s+true\b", template):
        return False
    return None


def _template_uses(template: str, variable: str) -> bool | None:
    if not template:
        return None
    try:
        parsed = Environment(extensions=["jinja2.ext.loopcontrols"]).parse(template)
        return any(node.name == variable and node.ctx == "load" for node in parsed.find_all(nodes.Name))
    except TemplateSyntaxError:
        return None


def reasoning_history_descriptor(metadata: GgufRuntimeMetadata, deployment: Deployment | None = None) -> RuntimeControlDescriptor:
    """Describe history replay only when the actual template gives evidence.

    The server capability says whether replay is understood, while the Jinja
    template determines what an omitted preserve_thinking value means.
    """
    props = deployment.server_props if deployment is not None else None
    template = props.chat_template if props is not None and props.chat_template else metadata.chat_template or ""
    template = re.sub(r"\{#.*?#\}", "", template, flags=re.DOTALL)
    if deployment is not None and not (props and props.chat_template) and any(
        deployment.applied_startup.get(key) for key in ("chat_template", "chat_template_file")
    ):
        template = ""
    caps = props.chat_template_caps if props is not None else {}
    declared = _template_uses(template, "preserve_thinking") or _template_uses(template, "preserve_reasoning")
    supported = caps.get("supports_preserve_reasoning")
    if supported is not False:
        supported = True if declared or supported is True else False if declared is False else None
    default = _template_boolean_default(template, "preserve_thinking")
    if default is None:
        default = _template_boolean_default(template, "preserve_reasoning")
    if supported is not True or not isinstance(default, bool):
        default = None
    return RuntimeControlDescriptor(
        key="reasoning_preserve", label="Thinking history",
        description="Keep or drop earlier thinking in later ordinary turns when the model template supports it.",
        source="server_template" if props is not None and props.chat_template else "gguf_template" if template else "unavailable",
        supported=supported, applied=default, default_value=default,
        default_source=("server_template" if props is not None and props.chat_template else "gguf_template") if default is not None else None,
        options=[RuntimeControlOption(value=value, label=label) for value, label in
                 (((True, "Keep"), (False, "Drop")) if default is not None else
                  ((None, "Auto"), (True, "Keep"), (False, "Drop")))] if supported is not False else [],
    )


def _template_efforts(template: str) -> tuple[set[str], set[str], bool]:
    template = re.sub(r"\{#.*?#\}", "", template, flags=re.DOTALL)
    variable = r"\b\w*reasoning_(?:effort|strength)\b"
    groups = re.findall(variable + r"\s+(?:not\s+)?in\s*[\[(]([^\])]+)[\])]", template)
    canonical = {value for group in groups for value in re.findall(r"['\"]([a-z]+)['\"]", group)}
    if not canonical:
        canonical = set(re.findall(variable + r"\s*==\s*['\"]([a-z]+)['\"]", template))
    # Only a closed, rejected-membership check is evidence that other values fail.
    closed = bool(re.search(variable + r"\s+not\s+in\s*[\[(][^\])]+[\])][^%]*%\}[^{}]*\{\{[-]?\s*raise_exception", template))
    aliases = set()
    for _name, alias, target in re.findall(
        r"\bif\s+(\w*reasoning_(?:effort|strength))\s*==\s*['\"]([a-z]+)['\"]\s*[-]?%\}\s*\{%[-]?\s*set\s+\1\s*=\s*['\"]([a-z]+)['\"]",
        template,
    ):
        if target in canonical:
            aliases.add(alias)
    return canonical, canonical | aliases, closed


def reasoning_budget_descriptor(deployment: Deployment | None, metadata: GgufRuntimeMetadata | None = None) -> RuntimeControlDescriptor:
    props = deployment.server_props if deployment is not None else None
    params = props.default_generation_settings.get("params", {}) if props else {}
    params = params if isinstance(params, dict) else {}
    observed = params.get("reasoning_budget_tokens")
    if observed is None and props:
        observed = props.default_generation_settings.get("reasoning_budget_tokens")
    explicit = props.chat_template_caps.get("supports_reasoning_budget") if props else None
    pinned_runtime = bool(props and props.build_info and props.build_info.startswith("b11045-"))
    template = props.chat_template if props and props.chat_template else metadata.chat_template if metadata else ""
    known_tags = bool(template and re.search(r"</think>|\[/THINK\]|<\|channel\|>analysis|<\|im_sep\|>.*analysis", template))
    no_thinking = bool(props and props.chat_template_caps.get("supports_thinking") is False)
    supported = explicit if isinstance(explicit, bool) else False if no_thinking else True if known_tags and (pinned_runtime or deployment is None) else None
    return RuntimeControlDescriptor(
        key="reasoning_budget_tokens", label="Thinking limit",
        description=("Maximum thinking tokens per response; the total response limit includes thinking and the answer."
                     if supported is True else "This endpoint's thinking limit is unsupported." if supported is False else
                     "Thinking-limit support has not been verified for this endpoint; the total response limit still applies."),
        source="pinned_runtime" if pinned_runtime and explicit is None and observed is None else "server_properties" if supported is not None else "unavailable",
        supported=supported, observed=observed, default_value=observed if type(observed) is int else -1,
        default_source="server_properties" if type(observed) is int else "pinned_runtime_default",
        options=[RuntimeControlOption(value=-1, label="Unlimited")] if supported is not False else [],
    )


def response_presets(descriptors: dict[str, RuntimeControlDescriptor]) -> list[ResponsePreset]:
    """Generic response bundles were not publisher/model recommendations."""
    return []


def validate_model_reasoning(deployment: Deployment, bag: SettingsBag) -> None:
    """Fail before dispatch for known-invalid inherited or explicit effort.

    Unknown templates stay usable with the bag's existing unverified marker.
    Do not silently lower effort or rewrite a frozen preset/run snapshot.
    """
    invalid = [key for key in bag.unsupported if key in PER_REQUEST_KEYS]
    if invalid:
        key = invalid[0]
        code = "invalid_reasoning_setting" if key == "reasoning" else "invalid_reasoning_budget" if key == "reasoning_budget_tokens" else "invalid_request_settings"
        raise HarnessError("Correct invalid response control values before sending.", code=code, status_code=422,
                           details={"keys": invalid})
    budget = bag.applied.get("reasoning_budget_tokens")
    if budget is not None:
        if type(budget) is not int or budget < -1:
            raise HarnessError("Thinking limit must be a whole token count, or -1 for unlimited thinking.",
                               code="invalid_reasoning_budget", status_code=422)
        if budget >= 0 and reasoning_budget_descriptor(deployment).supported is False:
            raise HarnessError("This endpoint does not support a thinking limit. Use the total response limit instead.",
                               code="model_reasoning_budget_unsupported", status_code=409,
                               details={"key": "reasoning_budget_tokens", "requested": budget})
    value = bag.applied.get("reasoning_effort")
    inherited_startup = value is None or value == "default"
    if inherited_startup:
        value = deployment.applied_startup.get("reasoning_effort")
    # b11045 server-common.cpp consumes top-level none as a
    # Thinking switch and erases reasoning_effort before Jinja evaluation.
    # It is not one of the selected template's constrained effort literals.
    if value is None or value in {"default", "none"}:
        return
    props = deployment.server_props
    if props is None:
        return
    canonical, accepted, closed = _template_efforts(props.chat_template or "")
    unsupported = props.chat_template_caps.get("supports_reasoning_effort") is False
    if unsupported or (closed and (not isinstance(value, str) or value not in accepted)):
        options = [item for item in _ordered_reasoning_efforts() if item in canonical] if not unsupported else []
        explanation = f"Supported levels: {', '.join(options)}." if options else "This template has no adjustable thinking levels."
        remedy = ("Change this model's launch setting and reload it." if inherited_startup else
                  "Update the selected preset or this message's thinking setting, or use the model default.")
        raise HarnessError(
            f"Thinking level '{value}' is not supported by this model. {explanation} {remedy}",
            code="model_reasoning_effort_unsupported", status_code=409,
            details={"key": "reasoning_effort", "requested": value, "supported": options,
                     "source": "server_template", "origin": "loaded_startup" if inherited_startup else "per_request"},
        )


def _speculative_descriptors(metadata: GgufRuntimeMetadata) -> dict[str, RuntimeControlDescriptor]:
    # b11045 recognizes an embedded MTP head by nextn.eh_proj tensor names.
    # N-gram modes need no auxiliary weights; model-specific draft architectures
    # are not offered until compatible head evidence is present.
    modes = [("none", "Off")]
    if metadata.has_mtp_tensors:
        modes.append(("draft-mtp", "MTP · built-in draft head"))
    modes.extend((value, label) for value, label in (
        ("ngram-simple", "N-gram · simple"), ("ngram-map-k", "N-gram · map"),
        ("ngram-map-k4v", "N-gram · map K4V"), ("ngram-mod", "N-gram · adaptive"),
        ("ngram-cache", "N-gram · cached")))
    return {
        "spec_type": RuntimeControlDescriptor(key="spec_type", flag="--spec-type", label="Speculative decoding",
            description="Drafts ahead to accelerate generation. MTP uses the model's recorded draft head. Speed varies with the model and workload.",
            source="gguf_tensor_directory" if metadata.has_mtp_tensors else "pinned_runtime_schema", applied="none",
            default_value="none", default_source="pinned_runtime_default", supported=True,
            options=[RuntimeControlOption(value=value, label=label) for value, label in modes]),
        "spec_draft_n_max": RuntimeControlDescriptor(key="spec_draft_n_max", flag="--spec-draft-n-max", label="Draft tokens",
            description="Maximum tokens drafted per step. The pinned runtime defaults to 3; benchmark your setup before increasing it.",
            source="pinned_runtime_default", applied=3, default_value=3, default_source="pinned_runtime_default", recommended=3, supported=True,
            options=[RuntimeControlOption(value=value, label=str(value)) for value in (1, 2, 3, 4, 6, 8, 12, 16)]),
    }


def _ordered_reasoning_efforts(supported: set[str] | None = None) -> list[str]:
    preferred = ["default", "minimal", "low", "medium", "high", "xhigh", "max"]
    supported = supported if supported is not None else set(preferred)
    ordered = [value for value in preferred if value in supported]
    ordered.extend(sorted(supported - set(ordered)))
    return ordered


def _title_effort(value: str) -> str:
    return value.replace("_", " ").title()


def _context_descriptor(maximum: int | None, observed: int | None) -> RuntimeControlDescriptor:
    options = [
        RuntimeControlOption(
            value="auto",
            label="Automatic fit",
            description="Let llama.cpp choose the largest context that fits this start.",
        ),
        RuntimeControlOption(value=0, label="Full model context", description="Use the model's full context; automatic fit cannot shrink it."),
    ]
    options.extend(
        RuntimeControlOption(
            value=value,
            label=_format_tokens(value),
            description=f"Start llama-server with --ctx-size {value}.",
        )
        for value in _context_values(maximum)
    )
    return RuntimeControlDescriptor(
        key="ctx_size",
        flag="--ctx-size",
        label="Context",
        description=(
            "Context capacity in tokens; simultaneous requests share the total pool. Automatic fit leaves "
            "--ctx-size unset; the observed value is recorded from /props once a "
            "server is healthy."
        ),
        source="gguf_metadata" if maximum is not None else "runtime_observation",
        applied=None,
        default_value=None,
        default_source="engine_default",
        observed=observed,
        minimum=min(1024, maximum) if type(maximum) is int and maximum > 0 else 1024,
        maximum=maximum,
        suggested_maximum=maximum if maximum is not None else 256 * 1024,
        options=options,
    )


def _gpu_layers_descriptor(block_count: int | None) -> RuntimeControlDescriptor:
    maximum = block_count + 1 if block_count is not None and block_count >= 0 else None
    if maximum is None:
        layer_values = ["auto", "all", 0]
    else:
        layer_values = ["auto", "all", *range(0, maximum + 1)]
    return RuntimeControlDescriptor(
        key="n_gpu_layers",
        flag="--n-gpu-layers",
        label="GPU layers",
        description=(
            "How many transformer layers llama.cpp should place on the GPU. "
            "Auto uses native placement and memory fitting when enabled; All requests full offload."
        ),
        source="gguf_metadata" if maximum is not None else "workbench_default",
        applied=DEFAULT_GPU_PROFILE["n_gpu_layers"],
        default_value=DEFAULT_GPU_PROFILE["n_gpu_layers"],
        default_source="pinned_runtime_default",
        maximum=maximum,
        options=[
            RuntimeControlOption(
                value=value,
                label="Automatic" if value == "auto" else "All" if value == "all" else "CPU" if value == 0 else str(value),
                description=(
                    "Start llama-server with --n-gpu-layers -1."
                    if value == -1
                    else f"Start llama-server with --n-gpu-layers {value}."
                ),
            )
            for value in layer_values
        ],
    )


def _startup_defaults(*, recommended_threads: int | None) -> dict[str, RuntimeControlDescriptor]:
    threads = _threads_descriptor(recommended_threads)
    return {
        "n_gpu_layers": RuntimeControlDescriptor(
            key="n_gpu_layers",
            flag="--n-gpu-layers",
            label="GPU layers",
            description="Native automatic placement; memory fitting is enabled initially.",
            source="pinned_runtime_default",
            applied=DEFAULT_GPU_PROFILE["n_gpu_layers"],
        ),
        "flash_attn": RuntimeControlDescriptor(
            key="flash_attn",
            flag="--flash-attn",
            label="Flash attention",
            description="Workbench lets the pinned runtime choose compatible flash attention by default.",
            source="pinned_runtime_default",
            applied=DEFAULT_GPU_PROFILE["flash_attn"],
            options=[
                RuntimeControlOption(value="on", label="On"),
                RuntimeControlOption(value="off", label="Off"),
                RuntimeControlOption(value="auto", label="Automatic"),
            ],
        ),
        "ctx_size": RuntimeControlDescriptor(
            key="ctx_size",
            flag="--ctx-size",
            label="Context",
            description="Omitted on a fresh launch so llama.cpp keeps its own context. Automatic fit and an explicit size are separate choices.",
            source="engine_default",
            applied=None,
        ),
        "threads": threads,
        "cache_type_k": RuntimeControlDescriptor(
            key="cache_type_k",
            flag="--cache-type-k",
            label="K cache",
            description="Pinned llama.cpp starts with f16 K cache unless this is overridden.",
            source="pinned_runtime_default",
            applied="f16",
        ),
        "kv_offload": RuntimeControlDescriptor(
            key="kv_offload", flag="--kv-offload / --no-kv-offload", label="KV placement",
            description="GPU follows each layer's device; CPU keeps the cache in RAM independently of weight offloading.",
            source="pinned_runtime_default", applied=True, supported=True,
            options=[RuntimeControlOption(value=True, label="GPU"), RuntimeControlOption(value=False, label="CPU")],
        ),
        "cache_type_v": RuntimeControlDescriptor(
            key="cache_type_v",
            flag="--cache-type-v",
            label="V cache",
            description="Pinned llama.cpp starts with f16 V cache unless this is overridden.",
            source="pinned_runtime_default",
            applied="f16",
        ),
        "fit": RuntimeControlDescriptor(
            key="fit",
            flag="--fit",
            label="Fit model to memory",
            description="Pinned llama.cpp fits the model to available memory unless this is overridden.",
            source="pinned_runtime_default",
            applied="on",
        ),
    }


def recommended_cpu_threads() -> int:
    physical = psutil.cpu_count(logical=False)
    logical = psutil.cpu_count(logical=True)
    return max(1, int(physical or logical or 1))


def _threads_descriptor(recommended_threads: int | None) -> RuntimeControlDescriptor:
    recommended = recommended_threads if recommended_threads is not None else recommended_cpu_threads()
    values = sorted({1, 2, 4, 8, 12, 16, recommended})
    values = [value for value in values if value <= max(recommended, 16)]
    return RuntimeControlDescriptor(
        key="threads",
        flag="--threads",
        label="CPU threads",
        description=(
            "llama.cpp defaults to -1 for automatic thread selection. Workbench recommends "
            "the detected CPU count when the user chooses an explicit value."
        ),
        source="pinned_runtime_default",
        applied=-1,
        default_value=-1,
        default_source="pinned_runtime_default",
        recommended=recommended,
        observed=None,
        maximum=None,
        suggested_maximum=recommended,
        options=[
            RuntimeControlOption(
                value=-1,
                label="Auto",
                description="Use --threads -1 for native automatic thread selection.",
            ),
            *[
                RuntimeControlOption(
                    value=value,
                    label=f"{value} threads" if value != 1 else "1 thread",
                    description=f"Start llama-server with --threads {value}.",
                )
                for value in values
            ],
        ],
    )


def _context_values(maximum: int | None) -> list[int]:
    if maximum is None or maximum < 1024:
        return []
    small = [value for value in SMALL_CONTEXT_VALUES if value <= maximum]
    if maximum < MIN_LARGE_CONTEXT_OPTION:
        return sorted({*small, maximum})
    values = {
        _round_to_1024(maximum * fraction)
        for fraction in CONTEXT_FRACTIONS
        if _round_to_1024(maximum * fraction) >= 1024
    }
    values.add(maximum)
    return sorted(value for value in values if value <= maximum)


def _round_to_1024(value: float) -> int:
    return int(round(value / 1024)) * 1024


def _format_tokens(value: int) -> str:
    if value % 1024 == 0:
        return f"{value // 1024}k"
    return f"{value:,}"
