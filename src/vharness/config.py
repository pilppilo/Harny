"""Endpoint configuration for any OpenAI-compatible server.

Resolution order (first wins):
    1. explicit CLI flags  (--base-url / --api-key / --model)
    2. environment         (VHARNESS_* with OPENAI_* fallbacks)
    3. TOML config profile (--profile <name> section)
    4. TOML config [default] section

Config files (first found wins):
    $VHARNESS_CONFIG, ~/.config/vharness/config.toml,
    ./vharness.toml (project-local), ./vharness.config.toml

Config file shape:

    # ~/.config/vharness/config.toml
    [default]
    base_url = "http://localhost:11434/v1"
    model = "qwen2.5-coder:7b"
    # api_key = "sk-..."            # local servers usually don't need one

    [openrouter]
    base_url = "https://openrouter.ai/api/v1"
    api_key = "sk-or-v1-..."
    model = "mistralai/mistral-small"

    [vllm]
    base_url = "http://localhost:8000/v1"
    model = "my-finetune"

Then: `--profile openrouter`, or rely on [default] when no profile is named.
API keys can live in the file or be overridden by env/flag — put secrets in
the user-level file (chmod 600), not in a committed project file.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # py3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover — bare 3.10 without tomli
        tomllib = None


class ConfigError(RuntimeError):
    pass


#: User-level config location (also settable via $VHARNESS_CONFIG).
USER_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vharness" / "config.toml"
PROJECT_CONFIGS = ("vharness.toml", "vharness.config.toml")

# Keys accepted in each profile section.
_SECTION_KEYS = ("base_url", "api_key", "model")


@dataclass
class EndpointConfig:
    base_url: str
    api_key: str
    model: str

    def describe(self) -> str:
        key = self.api_key[:4] + "…" if self.api_key else "(none)"
        return f"{self.base_url} model={self.model} key={key}"


def _load_toml(path: str | Path) -> dict:
    if tomllib is None:
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    except Exception as e:  # malformed TOML — visible, not fatal
        print(f"[!] ignoring unreadable config {path}: {e}", file=sys.stderr)
        return {}


def find_config_file(explicit: str | None = None) -> Path | None:
    """First existing config: $VHARNESS_CONFIG / explicit, user, project-local."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_path = os.environ.get("VHARNESS_CONFIG")
    if env_path and Path(env_path) not in candidates:
        candidates.append(Path(env_path))
    candidates.append(Path(USER_CONFIG))
    candidates.extend(Path(p) for p in PROJECT_CONFIGS)
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_profile(data: dict, profile: str | None) -> dict:
    """Merge [default] with the named profile (profile wins)."""
    merged: dict = {}
    base = data.get("default")
    if isinstance(base, dict):
        merged.update({k: base[k] for k in _SECTION_KEYS if k in base})
    if profile:
        section = data.get(profile)
        if not isinstance(section, dict):
            known = [k for k, v in data.items() if isinstance(v, dict) and k != "default"]
            raise ConfigError(
                f"config profile {profile!r} not found; available profiles: {known or 'none'}"
            )
        merged.update({k: section[k] for k in _SECTION_KEYS if k in section})
    return merged


def resolve_endpoint(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    *,
    env_prefix: str = "VHARNESS",
    profile: str | None = None,
    config_file: str | None = None,
) -> tuple[EndpointConfig, str]:
    """Resolve endpoint settings; returns (config, description-of-source)."""
    # 1) CLI flags — passed in non-None.
    # 2) environment.
    base_url = base_url or os.environ.get(f"{env_prefix}_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = api_key or os.environ.get(f"{env_prefix}_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = model or os.environ.get(f"{env_prefix}_MODEL") or os.environ.get("OPENAI_MODEL")

    # 3/4) config file profile (only fills gaps left by flags/env).
    config_src = "flags/env"
    if not (base_url and api_key is not None and model):
        cfg_path = find_config_file(config_file)
        if cfg_path is not None:
            data = _load_toml(cfg_path)
            section = load_profile(data, profile)
            if not base_url:
                base_url = section.get("base_url")
                config_src = f"config:{cfg_path}"
            if not api_key and "api_key" in section:
                api_key = section.get("api_key")
            if not model:
                model = section.get("model")
            if profile and not any(k in section for k in _SECTION_KEYS):
                config_src = f"config:{cfg_path}[{profile}]"

    if not model:
        raise ConfigError(
            "no model name: pass --model, set VHARNESS_MODEL, or add `model` to "
            f"{'profile ' + profile + ' in ' if profile else ''}a config file ({USER_CONFIG} or ./vharness.toml)"
        )
    if not base_url:
        raise ConfigError(
            "no endpoint: pass --base-url, set VHARNESS_BASE_URL, or add `base_url` to "
            f"{'profile ' + profile + ' in ' if profile else ''}a config file "
            "(any OpenAI-compatible server: Ollama, vLLM, llama.cpp, LM Studio, ...)"
        )
    if not api_key:
        # Many local servers accept any key; default rather than fail.
        api_key = "no-key"
    return EndpointConfig(base_url=base_url.rstrip("/"), api_key=api_key, model=model), config_src


# Backwards-compatible single-return helper (used by tests / external callers).
def resolve_endpoint_config(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    **kwargs,
) -> EndpointConfig:
    cfg, _src = resolve_endpoint(base_url, api_key, model, **kwargs)
    return cfg
