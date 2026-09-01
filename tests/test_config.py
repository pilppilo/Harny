"""Config file (TOML profiles) resolution."""

import pytest

from vharness.config import ConfigError, find_config_file, load_profile, resolve_endpoint

TOML = b"""
[default]
base_url = "http://localhost:11434/v1"
model = "qwen2.5-coder:7b"

[openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-v1-x"
model = "mistralai/mistral-small"
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "VHARNESS_BASE_URL", "VHARNESS_API_KEY", "VHARNESS_MODEL",
        "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "VHARNESS_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_bytes(TOML)
    monkeypatch.setattr("vharness.config.USER_CONFIG", path)
    return path


def test_default_section_fills_gaps(config):
    cfg, src = resolve_endpoint(None, None, None)
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model == "qwen2.5-coder:7b"
    assert cfg.api_key == "no-key"  # local server default
    assert "config" in src


def test_named_profile_overrides_default(config):
    cfg, _ = resolve_endpoint(None, None, None, profile="openrouter")
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.api_key == "sk-or-v1-x"
    assert cfg.model == "mistralai/mistral-small"


def test_flags_beat_profile(config):
    cfg, src = resolve_endpoint("http://flag:1/v1", None, "flag-model", profile="openrouter")
    assert cfg.base_url == "http://flag:1/v1"
    assert cfg.model == "flag-model"
    # per-field merge: key still from profile
    assert cfg.api_key == "sk-or-v1-x"
    assert src == "flags/env"


def test_env_beats_profile(config, monkeypatch):
    monkeypatch.setenv("VHARNESS_MODEL", "env-model")
    cfg, _ = resolve_endpoint(None, None, None, profile="openrouter")
    assert cfg.model == "env-model"
    assert cfg.base_url == "https://openrouter.ai/api/v1"  # rest from profile


def test_unknown_profile_lists_available(config):
    with pytest.raises(ConfigError) as e:
        resolve_endpoint(None, None, None, profile="nope")
    assert "openrouter" in str(e.value)


def test_missing_everything_shows_config_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("vharness.config.USER_CONFIG", tmp_path / "none.toml")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as e:
        resolve_endpoint(None, None, None)
    assert "VHARNESS_MODEL" in str(e.value) or "config file" in str(e.value)


def test_explicit_config_path_wins(tmp_path, monkeypatch):
    other = tmp_path / "other.toml"
    other.write_text('[mine]\nbase_url = "http://x:1/v1"\nmodel = "m"\n')
    monkeypatch.setattr("vharness.config.USER_CONFIG", tmp_path / "none.toml")
    cfg, _ = resolve_endpoint(None, None, None, profile="mine", config_file=str(other))
    assert cfg.model == "m"
    assert find_config_file(str(other)) == other


def test_malformed_toml_is_nonfatal(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("not [ valid toml ===")
    monkeypatch.setattr("vharness.config.USER_CONFIG", bad)
    monkeypatch.setenv("VHARNESS_MODEL", "m")
    monkeypatch.setenv("VHARNESS_BASE_URL", "http://x:1/v1")
    cfg, _ = resolve_endpoint(None, None, None)
    assert cfg.model == "m"  # env still works despite broken config


def test_load_profile_merges():
    data = {"default": {"model": "a", "base_url": "b"}, "p": {"model": "z"}}
    assert load_profile(data, None) == {"model": "a", "base_url": "b"}
    assert load_profile(data, "p") == {"model": "z", "base_url": "b"}
