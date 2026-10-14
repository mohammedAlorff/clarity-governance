import copy
import json

import httpx
from fastapi.testclient import TestClient


def test_api_exposes_selected_provider_and_blocks_missing_gemini_key(tmp_path, monkeypatch):
    from governance.app import create_app

    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-test')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'UNRELATED_SECRET')
    with TestClient(create_app(tmp_path / 'app.db')) as client:
        state = client.post('/api/connect', json={'mode': 'demo'}).json()
        assert state['settings']['provider'] == 'gemini'
        assert state['settings']['model'] == 'gemini-test'
        assert state['settings']['model_configured'] is False
        error = client.post('/api/inspect', json={'mode': 'agent'})
        assert error.status_code == 422
        assert 'GEMINI_API_KEY' in error.json()['detail']
        assert 'UNRELATED_SECRET' not in json.dumps(state) + error.text


def test_api_routes_gemini_and_records_provider_metadata(tmp_path, monkeypatch):
    import governance.app as app_module
    from governance.providers.gemini import GeminiClient

    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-test')
    monkeypatch.setenv('GEMINI_API_KEY', 'TEST_SECRET')
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                'status': 'completed',
                'steps': [
                    {
                        'type': 'model_output',
                        'content': [{'type': 'text', 'text': '{"proposals": []}'}],
                    }
                ],
                'usage': {
                    'total_input_tokens': 100,
                    'total_output_tokens': 10,
                    'total_thought_tokens': 5,
                    'total_cached_tokens': 0,
                },
            },
        )
    )
    monkeypatch.setattr(app_module, 'create_client', lambda: GeminiClient(transport=transport))
    with TestClient(app_module.create_app(tmp_path / 'app.db')) as client:
        client.post('/api/connect', json={'mode': 'demo'})
        response = client.post('/api/inspect', json={'mode': 'agent'})
        assert response.status_code == 200
        run = response.json()['inspections'][0]
        assert run['status'] == 'completed'
        assert run['provider'] == 'gemini'
        assert run['model'] == 'gemini-test'
        assert run['usage']['output_tokens'] == 15
        assert 'TEST_SECRET' not in response.text


def test_unknown_provider_keeps_demo_available(tmp_path, monkeypatch):
    from governance.app import create_app

    monkeypatch.setenv('LLM_PROVIDER', 'invalid')
    with TestClient(create_app(tmp_path / 'app.db')) as client:
        state = client.post('/api/connect', json={'mode': 'demo'})
        assert state.status_code == 200
        assert state.json()['settings']['model_configured'] is False
        assert client.post('/api/inspect', json={'mode': 'demo'}).status_code == 200
        assert client.post('/api/inspect', json={'mode': 'agent'}).status_code == 422


def test_evaluation_cli_uses_selected_provider(tmp_path, monkeypatch, capsys):
    from governance import providers
    from governance.evaluation import freeze_manifest, main
    from governance.source import DemoSource, MySQLSource
    from tests.test_evaluation import MANIFEST
    from tests.test_providers import EmptyGemini

    manifest = copy.deepcopy(MANIFEST)
    manifest['provider'], manifest['resolved_model'] = 'gemini', 'test-gemini'
    frozen = tmp_path / 'frozen.json'
    freeze_manifest(manifest, frozen)
    monkeypatch.setattr(providers, 'create_client', lambda: EmptyGemini())
    monkeypatch.setattr(MySQLSource, 'from_env', staticmethod(DemoSource))
    assert (
        main(
            [
                'trial',
                str(frozen),
                'C',
                str(tmp_path / 'trials'),
                '--source-hash',
                manifest['source_hash'],
            ]
        )
        == 0
    )
    artifacts = list((tmp_path / 'trials').glob('*.json'))
    assert len(artifacts) == 3
    assert all(json.loads(path.read_text())['provider'] == 'gemini' for path in artifacts)
