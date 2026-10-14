"""Provider selection must never fall through to another account or price."""

import json
import os
from unittest.mock import patch

import pytest

from governance.agent import run_inspection
from governance.source import DemoSource


def test_gemini_configuration_does_not_reuse_openai_key(monkeypatch):
    from governance.providers import create_client, model_settings

    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.8-flash')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'OPENAI_SECRET_CANARY')
    settings = model_settings()
    assert settings['provider'] == 'gemini'
    assert settings['configured'] is False
    assert settings['key_env'] == 'GEMINI_API_KEY'
    assert 'CANARY' not in json.dumps(settings)
    with pytest.raises(ValueError):
        create_client()


def test_provider_factory_preserves_explicit_openai_and_rejects_unknown(monkeypatch):
    from governance.providers import create_client
    from governance.providers.openai import OpenAIClient

    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_KEY')
    monkeypatch.setenv('OPENAI_MODEL', 'test-model')
    assert isinstance(create_client(), OpenAIClient)
    monkeypatch.setenv('LLM_PROVIDER', 'unconfigured-provider')
    with pytest.raises(ValueError):
        create_client()


def test_missing_gemini_reports_selected_provider_without_a_request(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.8-flash')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    result = run_inspection(DemoSource(), mode='agent')
    assert result['status'] == 'provider_unavailable'
    assert result['provider'] == 'gemini'
    assert result['model'] == 'gemini-3.8-flash'
    assert result['usage']['requests'] == 0


class EmptyGemini:
    provider = 'gemini'
    model = 'test-gemini'

    def respond(self, messages, tools, max_tokens, timeout):
        return {'proposals': [], 'usage': {'input_tokens': 100, 'output_tokens': 50}}


def test_gemini_cost_uses_only_gemini_prices():
    settings = {'OPENAI_INPUT_PRICE_PER_MILLION': '100', 'OPENAI_OUTPUT_PRICE_PER_MILLION': '200'}
    with patch.dict(os.environ, settings, clear=True):
        result = run_inspection(DemoSource(), EmptyGemini(), 'agent')
        assert result['usage']['cost_usd'] is None
    settings.update(GEMINI_INPUT_PRICE_PER_MILLION='0.75', GEMINI_OUTPUT_PRICE_PER_MILLION='3.75')
    with patch.dict(os.environ, settings, clear=True):
        result = run_inspection(DemoSource(), EmptyGemini(), 'agent')
        assert result['usage']['cost_usd'] == pytest.approx(0.0002625)
