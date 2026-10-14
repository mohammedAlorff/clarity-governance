from dataclasses import asdict
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from governance.app import create_app
from governance.contracts import RunLimits


@pytest.fixture
def connected(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'test-model')
    monkeypatch.setenv('GEMINI_API_KEY', 'PRIVATE_TEST_KEY')
    app = create_app(tmp_path / 'app.db')
    with TestClient(app) as client:
        assert client.post('/api/connect', json={'mode': 'demo'}).status_code == 200
        yield client, app


def test_preflight_counts_columns_without_source_or_provider_calls(connected, monkeypatch):
    client, app = connected
    original_schema = app.state.runtime['schema']
    app.state.runtime['schema'] = {
        'tables': [{'name': 'large', 'columns': [{'name': str(i)} for i in range(90)]}]
    }
    source = Mock(side_effect=AssertionError('Preflight must not query source'))
    app.state.runtime['source'] = source
    factory = Mock(side_effect=AssertionError('Preflight must not create provider'))
    monkeypatch.setattr('governance.app.create_client', factory)
    response = client.post('/api/inspect/preflight', json={'mode': 'fixed'})
    assert response.status_code == 200
    check = response.json()
    assert check['ready'] is False
    assert check['profile_calls_required'] == 91
    assert 'fixed_call_budget' in [issue['code'] for issue in check['issues']]
    assert check['limits'] == asdict(RunLimits())
    response = client.post(
        '/api/inspect/preflight', json={'mode': 'fixed', 'limits': {'max_calls': 100}}
    )
    assert response.json()['ready'] is True
    assert response.json()['provider_verified'] is False
    source.get_schema.assert_not_called()
    factory.assert_not_called()
    app.state.runtime['schema'] = original_schema
    assert client.get('/api/state').json()['inspections'] == []


def test_preflight_missing_key_privacy_and_demo_compatibility(connected, monkeypatch):
    client, app = connected
    monkeypatch.delenv('GEMINI_API_KEY')
    monkeypatch.setenv('PRIVACY_SAMPLE_RATE', '0.9')
    check = client.post('/api/inspect/preflight', json={'mode': 'agent'}).json()
    assert {item['code'] for item in check['issues']} == {'provider_configuration', 'privacy'}
    assert 'PRIVATE_TEST_KEY' not in str(check)
    monkeypatch.delenv('PRIVACY_SAMPLE_RATE')
    assert client.post('/api/inspect/preflight', json={'mode': 'demo'}).json()['ready']
    app.state.runtime['mode'] = 'mysql'
    check = client.post('/api/inspect/preflight', json={'mode': 'demo'}).json()
    assert check['ready'] is False
    assert check['issues'][0]['code'] == 'source_mode'


def test_custom_budget_enforced_and_saved_with_defaults(connected):
    client, _ = connected
    response = client.post('/api/inspect', json={'mode': 'demo', 'limits': {'max_calls': 1}})
    assert response.status_code == 200
    run = response.json()['inspections'][0]
    assert run['status'] == 'budget_exhausted'
    assert run['usage']['tool_calls'] == 1
    assert run['limits'] == {**asdict(RunLimits()), 'max_calls': 1}
    response = client.post('/api/inspect', json={'mode': 'demo'})
    assert response.status_code == 200
    assert response.json()['inspections'][0]['limits'] == asdict(RunLimits())


@pytest.mark.parametrize(
    'limits',
    [
        {'max_calls': 0},
        {'max_calls': 501},
        {'max_steps': 33},
        {'max_seconds': 601},
        {'max_tokens': 200001},
        {'max_output_tokens': 16001},
        {'max_retries': 4},
        {'max_calls': True},
        {'max_seconds': True},
        {'max_calls': '100'},
        {'unknown': 1},
    ],
)
def test_api_rejects_unsafe_or_ambiguous_budgets(connected, limits):
    client, _ = connected
    for endpoint in ('/api/inspect', '/api/inspect/preflight'):
        assert client.post(endpoint, json={'mode': 'demo', 'limits': limits}).status_code == 422


def test_run_limits_reject_boolean_time():
    with pytest.raises(ValueError):
        RunLimits(max_seconds=True)
