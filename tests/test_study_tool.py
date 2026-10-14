"""Offline pilot CLI contracts; no live MySQL or model requests."""

import importlib
import io
import json
from pathlib import Path

import pytest


def study_tool():
    try:
        return importlib.import_module('scripts.study_tool')
    except ModuleNotFoundError:
        pytest.fail('scripts.study_tool is missing')


SCHEMA = {
    'name': 'sakila_faults',
    'tables': [
        {
            'name': 'actor',
            'row_count': 10,
            'columns': [
                {'name': 'actor_id', 'data_type': 'int', 'nullable': False, 'key': 'PRI'},
                {'name': 'first_name', 'data_type': 'varchar', 'nullable': True, 'key': ''},
                {'name': 'last_name', 'data_type': 'varchar', 'nullable': True, 'key': ''},
            ],
        },
        {
            'name': 'film',
            'row_count': 10,
            'columns': [
                {'name': 'film_id', 'data_type': 'int', 'nullable': False, 'key': 'PRI'},
                {'name': 'title', 'data_type': 'varchar', 'nullable': True, 'key': ''},
                {'name': 'rental_rate', 'data_type': 'decimal', 'nullable': True, 'key': ''},
                {'name': 'rating', 'data_type': 'varchar', 'nullable': True, 'key': ''},
            ],
        },
        {
            'name': 'inventory',
            'row_count': 10,
            'columns': [
                {'name': 'inventory_id', 'data_type': 'int', 'nullable': False, 'key': 'PRI'},
                {'name': 'film_id', 'data_type': 'int', 'nullable': True, 'key': ''},
            ],
        },
        {
            'name': 'rental',
            'row_count': 10,
            'columns': [
                {'name': 'rental_id', 'data_type': 'int', 'nullable': False, 'key': 'PRI'},
                {'name': 'rental_date', 'data_type': 'datetime', 'nullable': True, 'key': ''},
                {'name': 'return_date', 'data_type': 'datetime', 'nullable': True, 'key': ''},
            ],
        },
    ],
    'relationships': [],
    'source_comment': 'password=hidden',
}


class FakeSource:
    def __init__(self):
        self.calls = []
        self.closed = False

    def get_schema(self):
        self.calls.append(('schema',))
        return SCHEMA

    def run_metric(self, metric_id, target, parameters):
        self.calls.append(('metric', metric_id, target, parameters))
        return {
            'metric_id': metric_id,
            'target': target,
            'status': 'completed',
            'eligible': 10,
            'passing': 9,
            'violations': 1,
            'row_count': 10,
            'null_count': 1,
            'non_null_count': 9,
            'distinct_count': 8,
            'violation_ids': [123],
            'secret': 'password=hidden',
        }

    def sample_column(self, table, column, limit):
        self.calls.append(('sample', table, column, limit))
        return {
            'table': table,
            'column': column,
            'samples': [
                {'type': 'string', 'length_bucket': '5-8'},
                {'type': 'string', 'length_bucket': '9-16', 'raw': 'PENELOPE'},
            ],
            'sample_count': 2,
            'redacted': True,
            'sampling': {'seed': 42},
        }

    def close(self):
        self.closed = True


def invoke(monkeypatch, tmp_path, args, source=None):
    tool = study_tool()
    monkeypatch.setattr(tool, 'LOG_DIR', tmp_path)
    source = source or FakeSource()
    monkeypatch.setattr(tool, '_open_fixture_source', lambda: source)
    output = io.StringIO()
    status = tool.main(['--run-id', 'pilot_1', *args], output=output)
    return status, json.loads(output.getvalue()), source


def log_entries(tmp_path):
    return [json.loads(line) for line in (tmp_path / 'pilot_1.jsonl').read_text().splitlines()]


def test_schema_is_projected_and_counts_as_an_action(monkeypatch, tmp_path):
    status, output, source = invoke(monkeypatch, tmp_path, ['schema'])
    assert status == 0
    assert output['result']['name'] == 'sakila_faults'
    assert len(output['result']['tables']) == 4
    assert 'password=hidden' not in json.dumps(output)
    assert source.closed
    log = log_entries(tmp_path)
    assert len(log) == 1
    assert log[0]['action'] == 'schema'
    assert log[0]['target'] is None
    assert log[0]['status'] == 'completed'
    assert log[0]['result'] == {'tables': 4, 'columns': 12, 'relationships': 0}
    assert log[0]['timestamp'].endswith('Z')


def test_profile_and_metric_hide_violation_ids_and_log_aggregates(monkeypatch, tmp_path):
    status, profile, source = invoke(monkeypatch, tmp_path, ['profile', 'actor', 'first_name'])
    assert status == 0
    assert profile['result']['null_count'] == 1
    assert 'violation_ids' not in json.dumps(profile)
    assert source.calls[-1] == ('metric', 'profile', {'table': 'actor', 'column': 'first_name'}, {})

    status, metric, source = invoke(
        monkeypatch,
        tmp_path,
        ['metric', 'range', 'film', 'rental_rate', '--parameters', '{"min":0,"max":10}'],
    )
    assert status == 0
    assert metric['result']['violations'] == 1
    assert 'violation_ids' not in json.dumps(metric)
    assert source.calls[-1] == (
        'metric',
        'range',
        {'table': 'film', 'column': 'rental_rate'},
        {'min': 0, 'max': 10},
    )
    assert [entry['action'] for entry in log_entries(tmp_path)] == ['profile', 'metric']
    assert log_entries(tmp_path)[1]['result'] == {'eligible': 10, 'passing': 9, 'violations': 1}


def test_sample_returns_only_bounded_shapes(monkeypatch, tmp_path):
    status, output, source = invoke(
        monkeypatch, tmp_path, ['sample', 'actor', 'first_name', '--limit', '2']
    )
    assert status == 0
    assert source.calls[-1] == ('sample', 'actor', 'first_name', 2)
    assert output['result']['shapes'] == [{'type': 'string', 'length_bucket': '5-8'}]
    assert output['result']['sample_count'] == 1
    assert 'PENELOPE' not in json.dumps(output)
    assert log_entries(tmp_path)[0]['result'] == {'sample_count': 1}


def test_invalid_metric_does_not_query_and_failure_does_not_echo_input(monkeypatch, tmp_path):
    status, output, source = invoke(
        monkeypatch,
        tmp_path,
        ['metric', 'range', 'film', 'title', '--parameters', '{"min":"password=hidden"}'],
    )
    assert status == 1
    assert source.calls == [('schema',)]
    assert 'password=hidden' not in json.dumps(output)
    assert source.closed
    assert log_entries(tmp_path)[0]['status'] == 'failed'
    assert 'password=hidden' not in (tmp_path / 'pilot_1.jsonl').read_text()


def test_run_budget_includes_schema_and_blocks_twenty_first_action(monkeypatch, tmp_path):
    tool = study_tool()
    monkeypatch.setattr(tool, 'LOG_DIR', tmp_path)
    opens = []

    def open_source():
        opens.append(1)
        return FakeSource()

    monkeypatch.setattr(tool, '_open_fixture_source', open_source)
    for _ in range(20):
        output = io.StringIO()
        assert tool.main(['--run-id', 'pilot_1', 'schema'], output=output) == 0
    output = io.StringIO()
    assert tool.main(['--run-id', 'pilot_1', 'schema'], output=output) == 1
    assert json.loads(output.getvalue())['error'] == 'Run action limit reached.'
    assert len(opens) == 20
    assert len(log_entries(tmp_path)) == 20


def test_connection_rejects_port_3306_before_transport(monkeypatch):
    tool = study_tool()
    values = {
        'MYSQL_HOST': '127.0.0.1',
        'MYSQL_PORT': '3306',
        'MYSQL_DATABASE': tool.SCHEMA,
        'MYSQL_USER': tool.USER,
        'MYSQL_PASSWORD': 'private-reader-value',
        'MYSQL_ALLOWED_TABLES': '',
        'MYSQL_QUERY_TIMEOUT_MS': '5000',
        'MYSQL_CONNECT_TIMEOUT': '5',
    }
    monkeypatch.setattr(tool, 'dotenv_values', lambda path: values)
    monkeypatch.setattr(
        tool.pymysql, 'connect', lambda **kwargs: pytest.fail('unexpected MySQL connection')
    )
    with pytest.raises(RuntimeError, match='Fixture configuration rejected'):
        tool._open_fixture_source()


def test_connection_uses_only_reader_and_verifies_instance_and_digest(monkeypatch, tmp_path):
    tool = study_tool()
    digest = 'a' * 64
    state = tmp_path / 'fault-fixture.json'
    state.write_text(
        json.dumps(
            {
                'fixture_version': 1,
                'schema': tool.SCHEMA,
                'fixture_rows_sha256': digest,
            }
        )
    )
    monkeypatch.setattr(tool, 'STATE', state)
    monkeypatch.setattr(
        tool,
        'dotenv_values',
        lambda path: {
            'MYSQL_HOST': '127.0.0.1',
            'MYSQL_PORT': str(tool.PORT),
            'MYSQL_DATABASE': tool.SCHEMA,
            'MYSQL_USER': tool.USER,
            'MYSQL_PASSWORD': 'private-reader-value',
            'MYSQL_ALLOWED_TABLES': '',
            'MYSQL_QUERY_TIMEOUT_MS': '5000',
            'MYSQL_CONNECT_TIMEOUT': '5',
        },
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, query):
            assert query.startswith('SELECT @@datadir')

        def fetchone(self):
            return {
                'directory': str(tool.DATADIR),
                'port': tool.PORT,
                'database_name': tool.SCHEMA,
            }

    class Connection:
        closed = False
        cursor_types = []

        def cursor(self, cursor_type=None):
            self.cursor_types.append(cursor_type)
            return Cursor()

        def close(self):
            self.closed = True

    connection = Connection()
    captured = {}

    def connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(tool.pymysql, 'connect', connect)

    def checked_snapshot(conn, schema):
        assert schema == tool.SCHEMA
        conn.cursor()
        assert connection.cursor_types[-1] is tool.pymysql.cursors.Cursor
        return digest

    monkeypatch.setattr(tool, 'snapshot', checked_snapshot)
    monkeypatch.setattr(tool, 'MySQLSource', lambda conn, schema: FakeSource())
    source = tool._open_fixture_source()
    assert isinstance(source, FakeSource)
    assert captured['host'] == '127.0.0.1'
    assert captured['port'] == 3307
    assert captured['user'] == 'sakila_fault_reader'
    assert captured['database'] == 'sakila_faults'
    assert captured['password'] == 'private-reader-value'


def test_wrong_datadir_closes_connection_without_exposing_exception(monkeypatch, tmp_path):
    tool = study_tool()
    monkeypatch.setattr(tool, 'STATE', tmp_path / 'state.json')
    tool.STATE.write_text(
        json.dumps(
            {
                'fixture_version': 1,
                'schema': tool.SCHEMA,
                'fixture_rows_sha256': 'a' * 64,
            }
        )
    )
    monkeypatch.setattr(
        tool,
        'dotenv_values',
        lambda path: {
            'MYSQL_HOST': '127.0.0.1',
            'MYSQL_PORT': str(tool.PORT),
            'MYSQL_DATABASE': tool.SCHEMA,
            'MYSQL_USER': tool.USER,
            'MYSQL_PASSWORD': 'private-reader-value',
            'MYSQL_ALLOWED_TABLES': '',
            'MYSQL_QUERY_TIMEOUT_MS': '5000',
            'MYSQL_CONNECT_TIMEOUT': '5',
        },
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, query):
            pass

        def fetchone(self):
            return {
                'directory': str(Path('C:/unrelated/mysql')),
                'port': 3307,
                'database_name': tool.SCHEMA,
            }

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(tool.pymysql, 'connect', lambda **kwargs: connection)
    with pytest.raises(RuntimeError, match='Fixture identity rejected'):
        tool._open_fixture_source()
    assert connection.closed
