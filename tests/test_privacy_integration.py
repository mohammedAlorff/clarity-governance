import json

from fastapi.testclient import TestClient

from governance.agent import run_inspection
from tests.test_agent import SequenceClient, Source, proposal


def test_model_run_records_checked_requests_and_withholds_raw_samples():
    client = SequenceClient(
        [
            {
                'calls': [
                    {
                        'name': 'sample_column',
                        'arguments': {'table': 'customers', 'column': 'email', 'limit': 10},
                        'call_id': 'call1',
                    }
                ]
            },
            {'proposals': [proposal()]},
        ]
    )
    result = run_inspection(Source(), client, 'agent')
    assert result['status'] == 'completed'
    assert result['privacy']['checked_requests'] == 2
    assert result['privacy']['blocked_requests'] == 0
    assert result['privacy']['raw_values_allowed'] is False
    assert 'CANARY' not in json.dumps(client.messages)


def test_privacy_gate_blocks_invalid_outbound_history_before_followup_request():
    client = SequenceClient(
        [
            {
                'calls': [
                    {
                        'name': 'run_metric',
                        'arguments': {
                            'metric_id': 'allowed_values',
                            'target': {'table': 'customers', 'column': 'email'},
                            'parameters': {'values': ['PRIVATE_PERSON@example.invalid']},
                        },
                        'call_id': 'call1',
                    }
                ]
            },
            {'proposals': [proposal()]},
        ]
    )
    result = run_inspection(Source(), client, 'agent')
    assert result['status'] == 'privacy_blocked'
    assert len(client.messages) == 1
    assert result['usage']['requests'] == 1
    assert result['privacy']['blocked_requests'] == 1
    assert 'PRIVATE_PERSON' not in json.dumps(result)


def test_privacy_state_and_export_distinguish_policy_from_untested_claims(tmp_path, monkeypatch):
    from governance.app import create_app

    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-test')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with TestClient(create_app(tmp_path / 'app.db')) as client:
        state = client.post('/api/connect', json={'mode': 'demo'}).json()
        privacy = state['privacy']
        assert privacy['policy']['raw_values_allowed'] is False
        assert privacy['policy']['sampling']['max_samples'] == 10
        assert privacy['policy']['schema_identifiers_visible'] is True
        assert privacy['accuracy_retention'] is None
        assert privacy['compliance_certified'] is False
        assert privacy['checked_requests'] == 0
        exported = client.get('/api/export/privacy')
        assert exported.status_code == 200
        assert exported.json() == privacy
        assert 'GEMINI_API_KEY' not in exported.text


def test_invalid_sampling_policy_stops_model_calls(monkeypatch):
    monkeypatch.setenv('PRIVACY_MAX_SAMPLES', '10000')
    client = SequenceClient([{'proposals': []}])
    result = run_inspection(Source(), client, 'agent')
    assert result['status'] == 'privacy_blocked'
    assert client.messages == []
