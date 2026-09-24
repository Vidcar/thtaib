"""Translate revision-pinned Hugging Face guidance for an installed GGUF.

GGUF and llama.cpp remain the tokenizer and template execution owners. This
module reads verified companions and records only settings with a safe mapping.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workbench_backend.inference.hf_fetch import HuggingFaceDownload, PUBLISHER_DIR, REPOSITORY_TEMPLATE_DIR
from workbench_backend.inference.inspect import read_gguf_runtime_metadata, _RuntimeMetadataReader, _close_reader
from workbench_backend.inference.schemas import HuggingFaceConfiguration, ModelBundle


def configuration_from_download(bundle: ModelBundle, download: HuggingFaceDownload) -> HuggingFaceConfiguration:
    by_name = {item.name: item for item in bundle.files}
    prefix = f"{PUBLISHER_DIR}/" if download.source_repo_id and download.source_revision else ""
    origin = "publisher" if prefix else "repository"
    generation = _read_json(by_name, prefix + "generation_config.json")
    defaults, unsupported = _generation_defaults(generation)
    if prefix:
        source_tokenizer = _read_json(by_name, prefix + "tokenizer.json")
    else:
        source_tokenizer = _read_json(by_name, "tokenizer.json")
    primary = Path(bundle.primary_path or "")
    try:
        metadata = read_gguf_runtime_metadata(primary)
    except (OSError, ValueError, KeyError, TypeError):
        metadata = None
        unsupported["gguf_metadata"] = "GGUF metadata could not be inspected; template and token comparisons are unverified."
    if isinstance(generation, dict) and "suppress_tokens" in generation:
        ids = generation["suppress_tokens"]
        if isinstance(ids, list) and ids and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in ids):
            if _token_ids_match(primary, source_tokenizer, ids):
                defaults["logit_bias"] = [[item, False] for item in ids]
            else:
                unsupported["suppress_tokens"] = "Source token IDs could not be matched to the GGUF tokenizer."
        else:
            unsupported["suppress_tokens"] = "Expected a nonempty list of token IDs."
    template_name = prefix + "chat_template.jinja"
    template_record = by_name.get(template_name) or by_name.get(
        (f"{PUBLISHER_DIR}/chat_template.from-tokenizer.jinja" if prefix
         else f"{REPOSITORY_TEMPLATE_DIR}/chat_template.from-tokenizer.jinja"))
    embedded = metadata.chat_template if metadata else None
    template_text = None
    if template_record is not None:
        try:
            template_text = Path(template_record.path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            unsupported["chat_template.jinja"] = "Template file could not be read as UTF-8."
    selected_origin = "gguf" if embedded else "none"
    selected_file = None
    differs = bool(template_text is not None and embedded and template_text != embedded)
    if template_text and (not embedded or not differs):
        selected_origin = origin
        selected_file = template_record.path if template_record else None
    elif template_text and differs:
        unsupported["chat_template.jinja"] = "Standalone template differs from GGUF; GGUF is selected until a compatible template choice is made."
    if not template_text and not embedded:
        unsupported["chat_template"] = "No usable standalone or embedded chat template was found."
    if _read_json(by_name, prefix + "config.json") is not None:
        unsupported["config.json runtime fields"] = "Architecture, tokenizer and context are taken from the GGUF and observed server."
    return HuggingFaceConfiguration(
        source_repo_id=download.source_repo_id,
        source_revision=download.source_revision,
        source_verified=bool(download.source_repo_id and download.source_revision),
        source_note="Conversion marker matched the pinned publisher commit." if prefix else "No verified external publisher source; repository files only.",
        template_origin=selected_origin,
        template_file=selected_file,
        template_differs=differs,
        generation_defaults=defaults,
        unsupported=unsupported,
    )


def _read_json(by_name: dict[str, Any], name: str) -> Any:
    record = by_name.get(name)
    if record is None:
        return None
    try:
        return json.loads(Path(record.path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _generation_defaults(config: Any) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(config, dict):
        return {}, {} if config is None else {"generation_config.json": "Expected a JSON object."}
    defaults: dict[str, Any] = {}
    unsupported: dict[str, str] = {}
    sampled = config.get("do_sample", True)
    if sampled is False:
        defaults["temperature"] = 0.0
    elif sampled is True:
        numeric = {"temperature": (0, 100), "top_p": (0, 1), "top_k": (0, 1000000),
            "min_p": (0, 1), "typical_p": (0, 1), "repetition_penalty": (0, 100)}
        for key, (minimum, maximum) in numeric.items():
            if key not in config:
                continue
            value = config[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not minimum < value <= maximum:
                unsupported[key] = "Invalid publisher sampling value."
                continue
            defaults["repeat_penalty" if key == "repetition_penalty" else key] = value
    else:
        unsupported["do_sample"] = "Expected true or false."
    limit = config.get("max_new_tokens")
    if limit is not None:
        if isinstance(limit, int) and not isinstance(limit, bool) and 0 < limit <= 1000000:
            defaults["max_tokens"] = limit
        else:
            unsupported["max_new_tokens"] = "Invalid publisher output limit."
    stops = config.get("stop_strings")
    if stops is not None:
        if isinstance(stops, str) and stops or isinstance(stops, list) and stops and all(isinstance(value, str) and value for value in stops):
            defaults["stop"] = [stops] if isinstance(stops, str) else stops
        else:
            unsupported["stop_strings"] = "Expected nonempty stop text."
    known = {"do_sample", "temperature", "top_p", "top_k", "min_p", "typical_p",
        "repetition_penalty", "max_new_tokens", "stop_strings", "suppress_tokens"}
    tokenizer = {"bos_token_id", "eos_token_id", "pad_token_id", "decoder_start_token_id"}
    for key in config.keys() - known:
        if key in tokenizer:
            unsupported[key] = "The GGUF tokenizer and runtime own special token handling."
        elif key != "transformers_version":
            unsupported[key] = "No verified llama.cpp request mapping is available."
    return defaults, unsupported


def _token_ids_match(gguf_path: Path, source_tokenizer: Any, ids: list[int]) -> bool:
    if not isinstance(source_tokenizer, dict):
        return False
    model = source_tokenizer.get("model")
    vocab = model.get("vocab") if isinstance(model, dict) else None
    expected: dict[int, str] = {}
    if isinstance(vocab, dict):
        expected.update({value: token for token, value in vocab.items() if isinstance(value, int) and value in ids})
    elif isinstance(vocab, list):
        for index in ids:
            if index < len(vocab):
                item = vocab[index]
                expected[index] = item[0] if isinstance(item, list) and item and isinstance(item[0], str) else item if isinstance(item, str) else ""
    for item in source_tokenizer.get("added_tokens") or []:
        if isinstance(item, dict) and item.get("id") in ids and isinstance(item.get("content"), str):
            expected[item["id"]] = item["content"]
    if len(expected) != len(set(ids)):
        return False
    try:
        reader = _RuntimeMetadataReader(str(gguf_path), "r")
        try:
            field = reader.fields.get("tokenizer.ggml.tokens")
            if field is None:
                return False
            return all(index < len(field.data) and _token_text(field.contents(index)) == expected[index]
                for index in ids)
        finally:
            _close_reader(reader)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _token_text(value: Any) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
