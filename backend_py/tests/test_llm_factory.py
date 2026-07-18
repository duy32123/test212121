from __future__ import annotations

import importlib

import pytest


def _reload_settings_and_factory(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.config.settings as settings_module
    import app.explanation.llm_factory as factory_module

    importlib.reload(settings_module)
    importlib.reload(factory_module)
    return factory_module


def test_deepseek_provider_default_base_url(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    factory = _reload_settings_and_factory(
        monkeypatch, LLM_PROVIDER="deepseek", LLM_API_KEY="dummy", LLM_MODEL="deepseek-chat"
    )
    llm = factory.get_default_llm()
    assert llm.model == "deepseek-chat"
    assert llm.api_base == "https://api.deepseek.com"


def test_deepseek_provider_custom_base_url(monkeypatch):
    factory = _reload_settings_and_factory(
        monkeypatch,
        LLM_PROVIDER="deepseek",
        LLM_API_KEY="dummy",
        LLM_MODEL="deepseek-chat",
        LLM_BASE_URL="https://my-proxy.example.com",
    )
    llm = factory.get_default_llm()
    assert llm.api_base == "https://my-proxy.example.com"


def test_anthropic_provider_still_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    factory = _reload_settings_and_factory(monkeypatch, LLM_API_KEY="dummy", LLM_MODEL="claude-sonnet-4-6")
    llm = factory.get_default_llm()
    assert llm.model == "claude-sonnet-4-6"


def test_openai_like_requires_base_url(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    factory = _reload_settings_and_factory(
        monkeypatch, LLM_PROVIDER="openai_like", LLM_API_KEY="dummy", LLM_MODEL="some-model"
    )
    with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        factory.get_default_llm()


def test_missing_api_key_raises_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    factory = _reload_settings_and_factory(monkeypatch, LLM_PROVIDER="deepseek")
    with pytest.raises(RuntimeError, match="API key"):
        factory.get_default_llm()


def test_unsupported_provider_raises_clear_error(monkeypatch):
    factory = _reload_settings_and_factory(monkeypatch, LLM_PROVIDER="unknown_provider", LLM_API_KEY="dummy")
    with pytest.raises(RuntimeError, match="không được hỗ trợ"):
        factory.get_default_llm()
