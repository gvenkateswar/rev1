"""Configuration loading for the video asset pipeline.

API keys and model settings come from a JSON config file (default:
``config.json`` in the project root). Environment variables take
precedence over file values, so secrets can be kept out of the file
entirely if preferred. Copy ``config.example.json`` to ``config.json``
to get started.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"

DEFAULT_SHOTLIST_MODEL = "claude-sonnet-4-6"


class ConfigError(Exception):
    """Raised when configuration is missing or malformed."""


@dataclass
class Config:
    anthropic_api_key: str
    rijksmuseum_api_key: str = ""
    smithsonian_api_key: str = ""
    shotlist_model: str = DEFAULT_SHOTLIST_MODEL


def load_config(path: Optional[Path] = None) -> Config:
    """Load pipeline configuration from a JSON file and the environment.

    The Anthropic API key is required; the Rijksmuseum and Smithsonian
    keys are optional placeholders for later stages.
    """
    path = path or DEFAULT_CONFIG_PATH

    file_values: dict = {}
    if path.exists():
        try:
            file_values = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config file {path} is not valid JSON: {exc}") from exc
        if not isinstance(file_values, dict):
            raise ConfigError(f"Config file {path} must contain a JSON object.")

    def pick(file_key: str, env_key: str, default: str = "") -> str:
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val
        val = file_values.get(file_key, default)
        return val if isinstance(val, str) else default

    anthropic_api_key = pick("anthropic_api_key", "ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ConfigError(
            f"No Anthropic API key found. Copy config.example.json to {path} "
            "and fill in 'anthropic_api_key', or set the ANTHROPIC_API_KEY "
            "environment variable."
        )

    return Config(
        anthropic_api_key=anthropic_api_key,
        rijksmuseum_api_key=pick("rijksmuseum_api_key", "RIJKSMUSEUM_API_KEY"),
        smithsonian_api_key=pick("smithsonian_api_key", "SMITHSONIAN_API_KEY"),
        shotlist_model=pick(
            "shotlist_model", "PIPELINE_SHOTLIST_MODEL", DEFAULT_SHOTLIST_MODEL
        ),
    )
