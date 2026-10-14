"""Saved MySQL work remains readable after restart without reconnecting its source."""

import pytest
from fastapi.testclient import TestClient

from governance.app import create_app
from governance.source import DemoSource, MySQLSource


@pytest.fixture
def saved_mysql_scope(tmp_path, monkeypatch):
    # Only replace the external connector: real metrics, storage, reviews and exports run.
    monkeypatch.setattr(MySQLSource, 'from_env', staticmethod(DemoSource))
    path = tmp_path / 'saved.db'
    app = create_app(path)
    with TestClient(app) as client:
        assert client.post('/api/connect', json={'mode': 'mysql'}).status_code == 200
        scope = app.state.runtime['scope']
        for kind in ('description', 'rule'):
            target = {'table': 'customers', 'column': 'email'}
            proposal = app.state.store.add_proposal(
                scope,
                {
                    'kind': kind,
                    'target': target,
                    'title': 'Customer email',
                    'description': 'Contact email supplied by the customer.',
                    'evidence': ['Confirmed by the test database owner.'],
                    'assumptions': [],
                    'rule': (
                        {'metric_id': 'completeness', 'target': target, 'parameters': {}}
                        if kind == 'rule'
                        else None
                    ),
                },
            )
            assert (
                client.post(
                    f'/api/proposals/{proposal["id"]}/review',
                    json={'action': 'approve', 'reviewer': 'test owner'},
                ).status_code
                == 200
            )
        app.state.store.add_record(
            scope,
            'inspection',
            {
                'provider': 'local',
                'model': 'offline-test',
                'status': 'completed',
                'inspected_targets': ['customers.email'],
                'privacy': {'checked_requests': 2, 'blocked_requests': 0},
            },
        )
        response = client.post('/api/checks/run', json={})
        assert response.status_code == 200
        before = response.json()
    return path, scope, before


def test_mysql_restart_restores_read_only_outputs_without_connecting(
    saved_mysql_scope, monkeypatch
):
    path, scope, before = saved_mysql_scope

    def unexpected_connect():
        raise AssertionError('Startup must not connect to MySQL.')

    monkeypatch.setattr(MySQLSource, 'from_env', staticmethod(unexpected_connect))
    app = create_app(path)
    with TestClient(app) as client:
        state = client.get('/api/state').json()
        assert state['source'] == {**before['source'], 'connected': False}
        assert app.state.runtime['scope'] == scope
        assert state['schema'] == before['schema']
        assert state['proposals'] == before['proposals']
        assert state['report'] == before['report']
        assert state['inspections'] == before['inspections']
        assert state['privacy']['checked_requests'] == 2
        dictionary = client.get('/api/dictionary')
        assert dictionary.status_code == 200
        email = next(
            column
            for column in dictionary.json()['columns']
            if column['table'] == 'customers' and column['column'] == 'email'
        )
        assert email['status'] == 'approved'
        assert email['description'] == 'Contact email supplied by the customer.'
        assert (
            'Contact email supplied by the customer.' in client.get('/api/export/dictionary').text
        )
        assert client.get('/api/export/report').json() == before['report']
        assert client.get('/api/export/privacy').json()['checked_requests'] == 2


def test_restored_mysql_blocks_source_actions_and_preflight(saved_mysql_scope):
    path, _, before = saved_mysql_scope
    with TestClient(create_app(path)) as client:
        preflight = client.post('/api/inspect/preflight', json={'mode': 'agent'}).json()
        assert preflight['ready'] is False
        assert 'source_disconnected' in {issue['code'] for issue in preflight['issues']}
        assert client.post('/api/inspect', json={'mode': 'agent'}).status_code == 409
        assert client.post('/api/checks/run', json={}).status_code == 409
        assert (
            client.post(
                f'/api/proposals/{before["proposals"][0]["id"]}/review',
                json={'action': 'edit', 'reviewer': 'test owner', 'changes': {'title': 'Edited'}},
            ).status_code
            == 409
        )
        assert client.get('/api/state').json()['proposals'] == before['proposals']


@pytest.mark.parametrize('mode', ['mysql', 'demo'])
def test_explicit_reconnect_starts_fresh_scope_and_keeps_saved_work(saved_mysql_scope, mode):
    path, old_scope, before = saved_mysql_scope
    app = create_app(path)
    with TestClient(app) as client:
        response = client.post('/api/connect', json={'mode': mode})
        assert response.status_code == 200
        assert response.json()['source']['connected'] is True
        assert response.json()['proposals'] == []
        assert response.json()['report'] is None
        assert app.state.runtime['scope'] != old_scope
        assert (
            client.post(
                f'/api/proposals/{before["proposals"][0]["id"]}/review',
                json={'action': 'edit', 'reviewer': 'test owner', 'changes': {'title': 'Edited'}},
            ).status_code
            == 409
        )
        assert app.state.store.proposals(old_scope) == before['proposals']
        assert app.state.store.records(old_scope, 'report')[0]['id'] == before['report']['id']


def test_failed_reconnect_preserves_cached_outputs(saved_mysql_scope, monkeypatch):
    path, scope, before = saved_mysql_scope

    def unavailable():
        raise ConnectionError('PRIVATE connection detail')

    monkeypatch.setattr(MySQLSource, 'from_env', staticmethod(unavailable))
    app = create_app(path)
    with TestClient(app) as client:
        response = client.post('/api/connect', json={'mode': 'mysql'})
        assert response.status_code == 422
        assert 'PRIVATE' not in response.text
        assert app.state.runtime['scope'] == scope
        assert client.get('/api/state').json()['report'] == before['report']


def test_unselected_source_does_not_have_a_dictionary(tmp_path):
    with TestClient(create_app(tmp_path / 'empty.db')) as client:
        assert client.get('/api/dictionary').status_code == 409
