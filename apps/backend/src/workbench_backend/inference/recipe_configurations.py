"""Explicitly turn pinned model-card response recipes into saved configurations."""

from __future__ import annotations

import hashlib
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError, nodes

from workbench_backend.errors import ManagerError
from workbench_backend.inference.configurations import ensure_model_configurations, model_default_values
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.inspect import read_gguf_runtime_metadata
from workbench_backend.inference.schemas import (
    BundleSourceKind,
    ResponseRecipe,
    ResponseRecipeConfigurationResult,
    ResponseRecipeOrigin,
    ModelBundle,
    RunProfile,
)
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore


def create_recipe_configurations(
    store: RecordStore,
    bundle_id: str,
    recipe_ids: list[str],
    default_recipe_id: str | None = None,
    *,
    base_configuration_id: str | None = None,
    configuration_namespace: str | None = None,
) -> ResponseRecipeConfigurationResult:
    """Validate the full choice first, then save each configuration once.

    The bundle default pointer is written last. A retry after a process failure
    recognizes already-created configurations by their immutable card origin.
    """
    with store.configuration_lock():
        bundle = store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown model.", code="bundle_missing", status_code=404)
        if bundle.source.kind != BundleSourceKind.huggingface:
            raise ManagerError("Response recipes are available for pinned Hugging Face models.",
                code="recipe_source", status_code=400)
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ManagerError("Choose each response recipe once.", code="recipe_duplicate", status_code=400)
        if default_recipe_id and default_recipe_id not in recipe_ids:
            raise ManagerError("The default recipe must also be selected.", code="recipe_default", status_code=400)
        available = {item.id: item for item in (bundle.huggingface_configuration.response_recipes
            if bundle.huggingface_configuration else [])}
        if any(recipe_id not in available for recipe_id in recipe_ids):
            raise ManagerError("Selected response recipes no longer match this pinned model card. Refresh the card and choose again.",
                code="recipe_stale", status_code=409)
        selected = [validate_response_recipe(bundle, recipe_id) for recipe_id in recipe_ids]
        ensure_model_configurations(store)
        bundle = store.get_bundle(bundle_id)
        assert bundle is not None
        base_id = base_configuration_id or bundle.default_configuration_id
        base = store.get_profile(base_id) if base_id else None
        if base is None:
            raise ManagerError("This model has no saved default configuration.", code="configuration_missing", status_code=409)
        profiles = [item for item in store.list_profiles() if item.bundle_id == bundle_id]
        names = {item.display_name.strip().casefold() for item in profiles}
        by_recipe = {_origin_key(item.recipe_origin): item for item in profiles if item.recipe_origin is not None}
        results: list[RunProfile] = []
        for recipe in selected:
            origin_key = _recipe_key(recipe)
            # A normal repeated card action preserves the user's edited recipe.
            # An import owns its distinct initial startup and stable retry ids.
            identity = ("profile_import_" + hashlib.sha256(
                repr((configuration_namespace, origin_key)).encode()).hexdigest()[:24]) if configuration_namespace else None
            profile = store.get_profile(identity) if identity else by_recipe.get(origin_key)
            if profile is None:
                requested = {**base.bags.per_request.requested, **recipe.per_request}
                if recipe.reasoning != "preserve":
                    requested["reasoning"] = recipe.reasoning
                now = utc_now()
                initial_startup, response_defaults = model_default_values(store, bundle, startup=base.bags.startup.requested)
                profile = RunProfile(
                    id=identity or new_id("profile"),
                    display_name=_unique_name(recipe.name, names),
                    bundle_id=bundle_id,
                    recipe_origin=ResponseRecipeOrigin(
                        recipe_id=recipe.id,
                        name=recipe.name,
                        source_repo_id=recipe.source_repo_id,
                        source_revision=recipe.source_revision,
                        card_sha256=recipe.card_sha256,
                        section=recipe.section,
                    ),
                    bags=resolve_bags(startup=dict(base.bags.startup.requested), per_request=requested,
                        startup_defaults=initial_startup, per_request_defaults=response_defaults),
                    settings_schema_version=2,
                    created_at=now,
                    updated_at=now,
                )
                store.put_profile(profile)
            by_recipe[origin_key] = profile
            results.append(profile)
        if default_recipe_id:
            chosen = by_recipe[_recipe_key(available[default_recipe_id])]
            bundle = store.put_bundle(bundle.model_copy(update={"default_configuration_id": chosen.id}))
        return ResponseRecipeConfigurationResult(bundle=bundle, configurations=results)


def _unique_name(name: str, used: set[str]) -> str:
    candidate = name
    if candidate.casefold() in used:
        candidate = f"{name} (model card)"
    index = 2
    while candidate.casefold() in used:
        candidate = f"{name} (model card {index})"
        index += 1
    used.add(candidate.casefold())
    return candidate


def _recipe_key(recipe: ResponseRecipe) -> tuple[str, str, str, str]:
    return (recipe.source_repo_id, recipe.source_revision, recipe.card_sha256, recipe.id)


def _origin_key(origin: ResponseRecipeOrigin) -> tuple[str, str, str, str]:
    return (origin.source_repo_id, origin.source_revision, origin.card_sha256, origin.recipe_id)


def validate_response_recipe(bundle: ModelBundle, recipe_id: str) -> ResponseRecipe:
    """Resolve one exact pinned recipe against the installed selected template."""
    recipe = next((item for item in (bundle.huggingface_configuration.response_recipes
        if bundle.huggingface_configuration else []) if item.id == recipe_id), None)
    if recipe is None:
        raise ManagerError("This recipe no longer matches the pinned model card. Refresh the card and choose again.",
                           code="recipe_stale", status_code=409)
    if recipe.reasoning != "preserve":
        _require_template_toggle(bundle, [recipe])
    from workbench_backend.inference.configuration_options import bundle_configuration_options
    from workbench_backend.inference.settings import normalize_per_request_requested

    _, invalid = normalize_per_request_requested(recipe.per_request)
    if invalid:
        raise ManagerError("The model-card recipe contains unsupported response values.",
                           code="recipe_values_invalid", status_code=409, details={"keys": invalid})
    effort = recipe.per_request.get("reasoning_effort")
    if effort not in {None, "default", "none"}:
        metadata = _selected_template_metadata(bundle)
        descriptor = bundle_configuration_options(bundle.id, metadata).per_request_defaults["reasoning_effort"]
        if descriptor.supported is False or descriptor.accepted_values is not None and effort not in descriptor.accepted_values:
            raise ManagerError("The selected template does not support this recipe's Thinking level.",
                               code="recipe_thinking_unsupported", status_code=409)
    return recipe


def validate_recipe_origin(bundle: ModelBundle, origin: ResponseRecipeOrigin) -> ResponseRecipeOrigin:
    recipe = validate_response_recipe(bundle, origin.recipe_id)
    expected = ResponseRecipeOrigin(recipe_id=recipe.id, name=recipe.name,
        source_repo_id=recipe.source_repo_id, source_revision=recipe.source_revision,
        card_sha256=recipe.card_sha256, section=recipe.section)
    if origin != expected:
        raise ManagerError("Recipe provenance no longer matches this exact pinned model card.",
                           code="recipe_stale", status_code=409)
    return expected


def _selected_template_metadata(bundle: ModelBundle):
    try:
        metadata = read_gguf_runtime_metadata(Path(bundle.primary_path or ""))
        config = bundle.huggingface_configuration
        if config and config.template_file:
            path = Path(config.template_file)
            record = next((item for item in bundle.files if Path(item.path) == path), None)
            payload = path.read_bytes()
            if record is None or len(payload) > 2 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != record.sha256:
                raise ValueError("selected template hash differs from the bundle record")
            metadata.chat_template = payload.decode("utf-8")
        return metadata
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise ManagerError("The selected model template could not be checked for Thinking levels.",
            code="recipe_template", status_code=409) from exc


def _require_template_toggle(bundle, recipes: list[ResponseRecipe]) -> None:
    config = bundle.huggingface_configuration
    if config and config.template_origin in {"repository", "publisher"} and config.template_file:
        try:
            template_path = Path(config.template_file)
            record = next((item for item in bundle.files if Path(item.path) == template_path), None)
            payload = template_path.read_bytes()
            if record is None or len(payload) > 2 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != record.sha256:
                raise ValueError("selected template hash differs from the bundle record")
            template = payload.decode("utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            raise ManagerError("The selected model template could not be checked for thinking support.",
                code="recipe_template", status_code=409) from exc
    else:
        try:
            template = read_gguf_runtime_metadata(Path(bundle.primary_path or "")).chat_template or ""
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ManagerError("The selected GGUF template could not be checked for thinking support.",
                code="recipe_template", status_code=409) from exc
    if not template:
        return  # Unknown capability remains usable; it is not incompatibility.
    try:
        parsed = Environment(extensions=["jinja2.ext.loopcontrols"]).parse(template)
        uses_toggle = any(node.name == "enable_thinking" and node.ctx == "load"
            for node in parsed.find_all(nodes.Name))
    except TemplateSyntaxError:
        return  # The native template engine remains authoritative.
    if not uses_toggle:
        raise ManagerError("This GGUF template does not verify the card's thinking and non-thinking modes.",
            code="recipe_thinking_unsupported", status_code=409)
