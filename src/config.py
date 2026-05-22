import json
import os
import tomllib
from pathlib import Path
from typing import Any, cast

from src.process import fail

DEFAULT_CONFIG = "config.toml"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_OPENCODE_ATTEMPTS = 2


def load_config(script_dir: Path) -> dict[str, Any]:
    config_path = Path(
        os.environ.get("OPENCODE_REVIEW_CONFIG", str(script_dir / DEFAULT_CONFIG))
    )
    try:
        with config_path.open("rb") as config_file:
            return tomllib.load(config_file)
    except FileNotFoundError:
        fail(f"config file not found: {config_path}")
    except tomllib.TOMLDecodeError as exc:
        fail(f"failed to parse TOML config {config_path}: {exc}")


def get_section(config: dict[str, Any], name: str) -> dict[str, Any]:
    section = config.get(name, {})
    if not isinstance(section, dict):
        fail(f"config section [{name}] must be a table")
    return cast(dict[str, Any], section)


def config_str(section: dict[str, Any], key: str, *, default: str | None = None) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value:
        fail(f"config value must be a non-empty string: {key}")
    return value


def config_str_list(section: dict[str, Any], key: str) -> list[str]:
    value = section.get(key, [])
    if not isinstance(value, list):
        fail(f"config value must be a list of strings: {key}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            fail(f"config value must be a list of non-empty strings: {key}")
        result.append(item)
    return result


def get_model_ids(model_section: dict[str, Any]) -> list[str]:
    primary_model = os.environ.get("OPENCODE_REVIEW_MODEL") or config_str(
        model_section, "id", default=DEFAULT_MODEL
    )
    fallback_models_env = os.environ.get("OPENCODE_REVIEW_FALLBACK_MODELS")
    if fallback_models_env:
        fallback_models = [
            model.strip() for model in fallback_models_env.split(",") if model.strip()
        ]
    else:
        fallback_models = config_str_list(model_section, "fallback_ids")

    model_ids: list[str] = []
    for model_id in [primary_model, *fallback_models]:
        if model_id not in model_ids:
            model_ids.append(model_id)
    return model_ids


def get_opencode_attempts() -> int:
    raw_value = os.environ.get("OPENCODE_REVIEW_ATTEMPTS")
    if raw_value is None:
        return DEFAULT_OPENCODE_ATTEMPTS
    try:
        attempts = int(raw_value)
    except ValueError:
        fail("OPENCODE_REVIEW_ATTEMPTS must be an integer")
    if attempts < 1:
        fail("OPENCODE_REVIEW_ATTEMPTS must be greater than zero")
    return attempts


def build_opencode_config(
    tmp_dir: Path,
    *,
    provider_id: str,
    provider_name: str,
    provider_npm: str,
    base_url: str,
    api_key_env: str,
    models: list[tuple[str, str]],
) -> Path:
    config: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: {
                "npm": provider_npm,
                "name": provider_name,
                "options": {
                    "baseURL": base_url,
                    "apiKey": f"{{env:{api_key_env}}}",
                },
                "models": {
                    model_id: {
                        "name": model_name,
                    }
                    for model_id, model_name in models
                },
            }
        },
    }

    config_path = tmp_dir / "opencode.json"
    _ = config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path
