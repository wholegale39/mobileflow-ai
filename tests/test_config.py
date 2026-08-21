"""测试 config 启动配置校验。"""
from __future__ import annotations

import os

import pytest

from mobileflow.config import (
    ConfigError,
    check_llm,
    check_paths,
    check_vision,
    validate_all,
)


def test_llm_missing_key_fails(monkeypatch):
    monkeypatch.delenv("MOBILEFLOW_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="MOBILEFLOW_API_KEY 未设置"):
        check_llm()


def test_llm_placeholder_key_fails(monkeypatch):
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "dummy")
    with pytest.raises(ConfigError, match="格式可疑"):
        check_llm()


def test_llm_valid_key_passes(monkeypatch):
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "sk-abc123xyz")
    monkeypatch.setenv("MOBILEFLOW_BASE_URL", "https://x.example/v1")
    assert check_llm()["ok"] is True


def test_llm_non_url_base_fails(monkeypatch):
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "sk-abc")
    monkeypatch.setenv("MOBILEFLOW_BASE_URL", "not-a-url")
    with pytest.raises(ConfigError, match="不是合法 URL"):
        check_llm()


def test_llm_strict_off_skips_key(monkeypatch):
    monkeypatch.delenv("MOBILEFLOW_API_KEY", raising=False)
    assert check_llm(strict_key=False)["ok"] is True


def test_vision_disabled_skips(monkeypatch):
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    assert check_vision(enabled=False)["enabled"] is False


def test_vision_enabled_missing_key_fails(monkeypatch):
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="未设置"):
        check_vision(enabled=True)


def test_vision_falls_back_to_agnes_key(monkeypatch):
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.setenv("AGNES_API_KEY", "sk-vision-key")
    assert check_vision(enabled=True)["ok"] is True


def test_paths_writable(tmp_path, monkeypatch):
    assert check_paths(tmp_path / "sub", must_writable=True)["ok"] is True


def test_paths_not_writable(tmp_path, monkeypatch):
    d = tmp_path / "ro"
    d.mkdir()
    os.chmod(d, 0o555)
    try:
        with pytest.raises(ConfigError, match="不可写"):
            check_paths(d, must_writable=True)
    finally:
        os.chmod(d, 0o755)


def test_validate_all_collects_all_issues(monkeypatch):
    monkeypatch.setenv("MOBILEFLOW_API_KEY", "dummy")
    monkeypatch.delenv("MOBILEFLOW_VISION_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    with pytest.raises(ConfigError) as ei:
        validate_all(vision_enabled=True)
    msg = ei.value.args[0]
    assert "LLM" in msg
    assert "Vision" in msg
