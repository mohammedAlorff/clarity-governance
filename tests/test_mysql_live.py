"""Opt-in contracts against the isolated, unmodified official Sakila dataset.

Run with GOVERNANCE_LIVE_MYSQL=1 after starting scripts/public_mysql.py.
These are automated integration checks, not model or human-review evidence.
The only write attempt inserts zero rows and must be denied by MySQL grants.
"""

import csv
import hashlib
import io
import json
import os
from pathlib import Path

import pymysql
import pytest
from dotenv import dotenv_values

from governance.source import MySQLSource

ROOT = Path(__file__).resolve().parents[1]
READER_ENV = ROOT / 'data' / 'public-mysql' / 'reader.env'
REVIEWER = 'automated integration test'
pytestmark = pytest.mark.skipif(
    os.getenv('GOVERNANCE_LIVE_MYSQL') != '1',
    reason='Set GOVERNANCE_LIVE_MYSQL=1 to verify the isolated public Sakila fixture.',
)


def _require_isolated_server(connection):
    """Refuse even the zero-row permission probe on any other MySQL server."""
    local_app_data = os.getenv('LOCALAPPDATA')
    if not local_app_data:
        pytest.fail(
            'LOCALAPPDATA is required to identify the isolated MySQL fixture.', pytrace=False
        )
    expected = Path(local_app_data) / 'Clarity' / 'public-mysql' / 'server-data'
    with connection.cursor() as cursor:
        cursor.execute('SELECT @@datadir AS datadir, @@port AS port, DATABASE() AS database_name')
        actual = cursor.fetchone()
    assert Path(actual['datadir']).resolve() == expected.resolve(), (
        'Refusing a non-fixture MySQL datadir.'
    )
    assert actual['port'] == 3307, 'Refusing a non-fixture MySQL port.'
    assert actual['database_name'] == 'sakila', 'Refusing a non-fixture schema.'


def _snapshot(source):
    """Digest every base-table row without printing or exporting source values."""
    digest = hashlib.sha256()
    counts = {}
    for table in sorted(source.get_schema()['tables'], key=lambda item: item['name']):
        name = table['name']
        keys = [column['name'] for column in table['columns'] if column['key'] == 'PRI']
        assert keys, 'The official Sakila base tables must have primary keys.'
        ordering = ','.join(f'`{key}`' for key in keys)
        digest.update(name.encode('utf-8'))
        count = 0
        with source.connection.cursor() as cursor:
            cursor.execute(f'SELECT * FROM `sakila`.`{name}` ORDER BY {ordering}')
            while rows := cursor.fetchmany(1000):
                for row in rows:
                    digest.update(json.dumps(row, sort_keys=True, default=repr).encode('utf-8'))
                    digest.update(b'\n')
                count += len(rows)
        counts[name] = count
    return counts, digest.hexdigest()


@pytest.fixture(scope='module')
def live_environment():
    if not READER_ENV.is_file():
        pytest.fail(
            'Live MySQL was enabled but data/public-mysql/reader.env is missing. Set up the public-data lab first.',
            pytrace=False,
        )
    settings = dotenv_values(READER_ENV)
    if not settings or any(
        not key.startswith('MYSQL_') or value is None for key, value in settings.items()
    ):
        pytest.fail(
            'The public-data reader.env must contain only populated MYSQL_* settings.',
            pytrace=False,
        )
    expected = {
        'MYSQL_HOST': '127.0.0.1',
        'MYSQL_PORT': '3307',
        'MYSQL_DATABASE': 'sakila',
        'MYSQL_USER': 'governance_reader',
    }
    if any(settings.get(key) != value for key, value in expected.items()):
        pytest.fail('reader.env does not identify the isolated public-data fixture.', pytrace=False)
    with pytest.MonkeyPatch.context() as patch:
        for key in list(os.environ):
            if key.startswith('MYSQL_'):
                patch.delenv(key)
        for key, value in settings.items():
            patch.setenv(key, value)
        yield


@pytest.fixture(scope='module')
def source(live_environment):
    try:
        live = MySQLSource.from_env()
    except (ValueError, RuntimeError):
        pytest.fail(
            'Cannot open the isolated read-only Sakila fixture. Start it with scripts/public_mysql.py start.',
            pytrace=False,
        )
    try:
        _require_isolated_server(live.connection)
        before = _snapshot(live)
        yield live
        assert _snapshot(live) == before, 'Live integration checks changed the source dataset.'
    finally:
        live.close()


def test_sakila_fixed_workflow_can_profile_all_columns_with_explicit_budget(source, monkeypatch):
    from governance.agent import run_inspection
    from governance.contracts import RunLimits
    from governance.readiness import inspection_readiness
    from tests.test_providers import EmptyGemini

    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'test-gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'MOCK_TRANSPORT_ONLY')
    schema = source.get_schema()
    assert not inspection_readiness(schema, 'mysql', 'fixed')['ready']
    limits = RunLimits(max_calls=100, max_seconds=120, max_tokens=64000)
    assert inspection_readiness(schema, 'mysql', 'fixed', limits)['ready']
    # Real MySQL reads, simulated model output: this does not measure AI quality.
    result = run_inspection(source, EmptyGemini(), 'fixed', limits)
    assert result['status'] == 'completed'
    assert result['profiled_columns'] == 90
    assert result['usage']['tool_calls'] == 91
    assert result['limits']['max_calls'] == 100


def test_sakila_schema_profiles_and_samples_are_redacted(source):
    schema = source.get_schema()
    assert schema['name'] == 'sakila'
    assert len(schema['tables']) == 16
    assert sum(len(table['columns']) for table in schema['tables']) == 90
    assert len(schema['relationships']) == 22
    counts = {table['name']: table['row_count'] for table in schema['tables']}
    assert {name: counts[name] for name in ('actor', 'film', 'inventory', 'rental', 'payment')} == {
        'actor': 200,
        'film': 1000,
        'inventory': 4581,
        'rental': 16044,
        'payment': 16044,
    }
    assert {
        'table': 'film',
        'column': 'language_id',
        'reference_table': 'language',
        'reference_column': 'language_id',
        'declared': True,
    } in schema['relationships']
    profile = source.run_metric('profile', {'table': 'actor', 'column': 'first_name'}, {})
    assert profile['status'] == 'completed'
    assert (
        profile['row_count'],
        profile['non_null_count'],
        profile['null_count'],
        profile['distinct_count'],
    ) == (200, 200, 0, 128)
    samples = source.sample_column('actor', 'first_name', 8)
    assert samples['redacted'] is True
    assert samples['sample_count'] == 8
    assert all(
        set(sample) == {'type', 'length_bucket'} and sample['type'] == 'string'
        for sample in samples['samples']
    )
    encoded = json.dumps([profile, samples])
    assert 'PENELOPE' not in encoded
    assert 'NICK' not in encoded
    assert 'min' not in profile and 'max' not in profile


@pytest.mark.parametrize(
    'metric,table,column,parameters,eligible,violations,ids',
    [
        ('completeness', 'film', 'original_language_id', {}, 1000, 1000, list(range(1, 101))),
        ('uniqueness', 'language', 'last_update', {}, 6, 6, [1, 2, 3, 4, 5, 6]),
        ('range', 'actor', 'actor_id', {'min': 3, 'max': 198}, 200, 4, [1, 2, 199, 200]),
        (
            'allowed_values',
            'language',
            'name',
            {'values': ['English', 'Italian', 'Japanese', 'Mandarin', 'French']},
            6,
            1,
            [6],
        ),
        ('pattern', 'language', 'name', {'pattern': '^E[a-z]+$'}, 6, 5, [2, 3, 4, 5, 6]),
        (
            'column_compare',
            'rental',
            'return_date',
            {'other_column': 'rental_date', 'operator': '>='},
            15861,
            0,
            [],
        ),
        (
            'referential',
            'film',
            'language_id',
            {'reference_table': 'language', 'reference_column': 'language_id'},
            1000,
            0,
            [],
        ),
    ],
    ids=[
        'completeness-bounded-ids',
        'uniqueness-all-duplicate-members',
        'numeric-range',
        'allowed-values',
        'mysql-pattern',
        'datetime-compare-excludes-nulls',
        'declared-reference',
    ],
)
def test_live_metric_contracts(
    source, metric, table, column, parameters, eligible, violations, ids
):
    result = source.run_metric(metric, {'table': table, 'column': column}, parameters)
    assert result['status'] == 'completed'
    assert (result['eligible'], result['passing'], result['violations']) == (
        eligible,
        eligible - violations,
        violations,
    )
    assert result['violation_ids'] == ids
    assert result['eligible_population']
    assert result['null_handling']
    json.dumps(result, allow_nan=False)


def test_reference_without_non_null_keys_is_not_a_pass(source):
    result = source.run_metric(
        'referential',
        {'table': 'film', 'column': 'original_language_id'},
        {'reference_table': 'language', 'reference_column': 'language_id'},
    )
    assert result['status'] == 'no_eligible_data'
    assert (
        result['eligible'],
        result['passing'],
        result['violations'],
        result['violation_ids'],
    ) == (0, 0, 0, [])


def test_reader_grants_deny_even_a_zero_row_insert(source):
    _require_isolated_server(source.connection)
    before = _snapshot(source)
    with pytest.raises(pymysql.MySQLError) as failure:
        with source.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sakila.actor (first_name,last_name) SELECT 'INTEGRATION','PROBE' WHERE 1=0"
            )
    # 1142 is a grant denial, rather than relying only on transaction read-only.
    assert failure.value.args[0] == 1142
    assert _snapshot(source) == before


def _draft(metric, table, column, parameters):
    target = {'table': table, 'column': column}
    return {
        'kind': 'rule',
        'target': target,
        'title': f'Integration contract: {metric}',
        'description': 'Explicit automated test rule; not a recommended business constraint.',
        'evidence': ['Supplied by the integration harness; not a model or human-review result.'],
        'assumptions': [],
        'rule': {'metric_id': metric, 'target': target, 'parameters': parameters},
    }


def test_live_api_review_versions_execution_and_exports(source, tmp_path, monkeypatch):
    # Even importing app.py must use temporary SQLite state for this test.
    monkeypatch.setenv('GOVERNANCE_DB', str(tmp_path / 'module-state.db'))
    from fastapi.testclient import TestClient

    from governance.app import create_app

    app = create_app(tmp_path / 'review-flow.db')

    def post(client, path, data):
        response = client.post(path, json=data)
        assert response.status_code == 200, response.text
        return response.json()

    def review(client, proposal, action, **kwargs):
        return post(
            client,
            '/api/proposals/' + proposal['id'] + '/review',
            {'action': action, 'reviewer': REVIEWER, **kwargs},
        )

    try:
        with TestClient(app) as client:
            connected = post(client, '/api/connect', {'mode': 'mysql'})
            assert connected['source'] == {'mode': 'mysql', 'name': 'sakila', 'connected': True}
            assert connected['proposals'] == [] and connected['report'] is None
            assert client.post('/api/inspect', json={'mode': 'demo'}).status_code == 422
            assert client.post('/api/checks/run', json={}).status_code == 409
            store = app.state.store
            scope = app.state.runtime['scope']
            complete = store.add_proposal(scope, _draft('completeness', 'language', 'name', {}))
            rejected = store.add_proposal(
                scope, _draft('pattern', 'language', 'name', {'pattern': '^E[a-z]+$'})
            )
            original = store.add_proposal(scope, _draft('range', 'actor', 'actor_id', {'max': 200}))
            description = store.add_proposal(
                scope,
                {
                    'kind': 'description',
                    'target': {'table': 'actor', 'column': 'first_name'},
                    'title': 'Actor given name',
                    'description': 'Actor given name in the public Sakila fixture.',
                    'evidence': ['Explicit integration-test description; not AI output.'],
                    'assumptions': [],
                },
            )
            review(client, complete, 'approve')
            review(client, rejected, 'reject')
            review(client, original, 'approve')
            review(client, description, 'approve')
            assert client.get('/api/state').json()['report'] is None
            first = post(client, '/api/checks/run', {})['report']
            assert {row['proposal_id'] for row in first['results']} == {
                complete['id'],
                original['id'],
            }
            assert all(row['violations'] == 0 for row in first['results'])
            assert first['outdated'] is False

            edited = review(
                client,
                original,
                'edit',
                changes={
                    'rule': {
                        'metric_id': 'range',
                        'target': original['target'],
                        'parameters': {'max': 198},
                    },
                },
            )
            replacement = next(
                p for p in edited['proposals'] if p['lineage_id'] == original['lineage_id']
            )
            assert replacement['version'] == 2 and replacement['status'] == 'draft'
            assert edited['report']['outdated'] is True
            without_reapproval = post(client, '/api/checks/run', {})['report']
            assert [row['proposal_id'] for row in without_reapproval['results']] == [complete['id']]
            review(client, replacement, 'approve')
            final = post(client, '/api/checks/run', {})['report']
            assert {row['proposal_id'] for row in final['results']} == {
                complete['id'],
                replacement['id'],
            }
            changed = next(
                row for row in final['results'] if row['proposal_id'] == replacement['id']
            )
            assert (
                changed['eligible'],
                changed['passing'],
                changed['violations'],
                changed['violation_ids'],
            ) == (200, 198, 2, [199, 200])
            assert all(
                row['reviewer'] == REVIEWER and row['approved_at'] for row in final['results']
            )
            assert final['models'] == [] and final['inspection_ids'] == []
            assert final['outdated'] is False
            exported = client.get('/api/export/report')
            assert exported.status_code == 200 and exported.json() == final
            dictionary = client.get('/api/export/dictionary')
            assert dictionary.status_code == 200
            assert 'text/csv' in dictionary.headers['content-type']
            rows = list(csv.DictReader(io.StringIO(dictionary.text)))
            assert len(rows) == 90
            actor_name = next(
                row for row in rows if (row['table'], row['column']) == ('actor', 'first_name')
            )
            assert actor_name['status'] == 'approved'
            assert actor_name['description'] == description['description']
            history = store.get_proposal(replacement['id'])['history']
            assert [entry['version'] for entry in history] == [1, 2]
            assert [entry['action'] for entry in history[0]['reviews']] == ['approve', 'edit']
    finally:
        if app.state.runtime['source'] is not None:
            app.state.runtime['source'].close()
