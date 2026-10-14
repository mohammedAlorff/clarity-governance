"""Bounded read-only JSON tool for the offline Sakila fault-fixture pilot.

Usage::

    python -m scripts.study_tool --run-id pilot_1 schema
    python -m scripts.study_tool --run-id pilot_1 profile actor first_name
    python -m scripts.study_tool --run-id pilot_1 metric range film rental_rate --parameters '{"min":0,"max":10}'
    python -m scripts.study_tool --run-id pilot_1 sample actor first_name --limit 2

Each invocation uses one of 20 actions in its run. The fixed fixture reader
can query only the isolated 127.0.0.1:3307 sakila_faults schema. Output is
schema metadata, aggregate counts, or redacted shape descriptors; raw values,
violation row IDs, credentials, and source exceptions are never printed.
"""

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from dotenv import dotenv_values

from governance.privacy import model_view, sample_shapes
from governance.quality import METRIC_DIMENSIONS, validate_rule
from governance.source import MySQLSource
from scripts.public_data_faults import COLUMNS, ENV, SCHEMA, STATE, USER, snapshot
from scripts.public_mysql import DATADIR, PORT, ROOT

LOG_DIR = ROOT / 'data' / 'study-pilot'
MAX_ACTIONS = 20
MAX_RESULT_BYTES = 16_384
RUN_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
_GENERIC_ERROR = 'Request rejected or fixture unavailable.'


class _TupleCursorConnection:
    """Match the tuple-row encoding used when the fixture digest was created."""

    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return self.connection.cursor(pymysql.cursors.Cursor)


def _open_fixture_source():
    """Open only the installed SELECT-only fixture reader after fixed checks."""
    values = dotenv_values(ENV)
    expected = {
        'MYSQL_HOST': '127.0.0.1',
        'MYSQL_PORT': '3307',
        'MYSQL_DATABASE': SCHEMA,
        'MYSQL_USER': USER,
        'MYSQL_ALLOWED_TABLES': '',
        'MYSQL_QUERY_TIMEOUT_MS': '5000',
        'MYSQL_CONNECT_TIMEOUT': '5',
    }
    if (
        PORT != 3307
        or set(values) != set(expected) | {'MYSQL_PASSWORD'}
        or any(values.get(key) != value for key, value in expected.items())
        or not values.get('MYSQL_PASSWORD')
    ):
        raise RuntimeError('Fixture configuration rejected')
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
        digest = state['fixture_rows_sha256']
        if (
            state.get('fixture_version') != 1
            or state.get('schema') != SCHEMA
            or not isinstance(digest, str)
            or not re.fullmatch(r'[0-9a-f]{64}', digest)
        ):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise RuntimeError('Fixture state rejected') from None
    try:
        connection = pymysql.connect(
            host='127.0.0.1',
            port=3307,
            user=USER,
            password=values['MYSQL_PASSWORD'],
            database=SCHEMA,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=5,
            read_timeout=6,
            write_timeout=6,
            charset='utf8mb4',
        )
    except Exception:
        raise RuntimeError('Fixture connection failed') from None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT @@datadir AS directory, @@port AS port, DATABASE() AS database_name'
            )
            server = cursor.fetchone()
        if (
            not isinstance(server, dict)
            or Path(server['directory']).resolve() != DATADIR.resolve()
            or int(server['port']) != 3307
            or server['database_name'] != SCHEMA
            or snapshot(_TupleCursorConnection(connection), SCHEMA) != digest
        ):
            raise ValueError
        source = MySQLSource(connection, SCHEMA)
        tables = source.get_schema()['tables']
        if (
            {table['name'] for table in tables} != set(COLUMNS)
            or len(tables) != len(COLUMNS)
            or any(
                table['row_count'] != 10
                or tuple(column['name'] for column in table['columns']) != COLUMNS[table['name']]
                or table['columns'][0]['key'] != 'PRI'
                for table in tables
            )
        ):
            source.close()
            raise ValueError
        return source
    except Exception:
        connection.close()
        raise RuntimeError('Fixture identity rejected') from None


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate parameter')
        result[key] = value
    return result


def _parameters(text):
    if len(text) > 4000:
        raise ValueError('Metric parameters exceed the limit')
    value = json.loads(
        text,
        object_pairs_hook=_unique_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid constant')),
    )
    if not isinstance(value, dict):
        raise ValueError('Metric parameters must be an object')
    return value


def _project(action, raw):
    projected = model_view(raw)
    if action == 'sample':
        projected.update(sample_shapes(raw))
    if not isinstance(projected, dict):
        raise ValueError('Unexpected source response')
    encoded = json.dumps(projected, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode('utf-8')) > MAX_RESULT_BYTES:
        raise ValueError('Projected result exceeds the limit')
    return projected


def _perform(source, args):
    if args.action == 'schema':
        raw = source.get_schema()
    else:
        target = {'table': args.table, 'column': args.column}
        schema = source.get_schema()
        if args.action == 'sample':
            validate_rule({'metric_id': 'profile', 'target': target, 'parameters': {}}, schema)
            if not 1 <= args.limit <= 10:
                raise ValueError('Sample limit rejected')
            raw = source.sample_column(args.table, args.column, args.limit)
        else:
            metric_id = 'profile' if args.action == 'profile' else args.metric_id
            parameters = {} if args.action == 'profile' else _parameters(args.parameters)
            validate_rule(
                {'metric_id': metric_id, 'target': target, 'parameters': parameters}, schema
            )
            raw = source.run_metric(metric_id, target, parameters)
    result = _project(args.action, raw)
    if args.action == 'schema':
        summary = {
            'tables': len(result.get('tables', [])),
            'columns': sum(len(table.get('columns', [])) for table in result.get('tables', [])),
            'relationships': len(result.get('relationships', [])),
        }
    elif args.action == 'sample':
        summary = {'sample_count': result['sample_count']}
    elif args.action == 'profile':
        summary = {
            key: result[key]
            for key in ('row_count', 'null_count', 'non_null_count', 'distinct_count')
        }
    else:
        summary = {key: result[key] for key in ('eligible', 'passing', 'violations')}
    return result, summary


@contextmanager
def _locked_run(path):
    """Serialize action counting and logging across CLI processes."""
    lock_path = path.with_suffix('.lock')
    if path.is_symlink() or lock_path.is_symlink():
        raise RuntimeError('Run path rejected')
    with lock_path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt

            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _action_count(path):
    if not path.exists():
        return 0
    with path.open(encoding='utf-8') as handle:
        return sum(1 for _ in handle)


def _append_log(path, entry):
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry, separators=(',', ':'), allow_nan=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--run-id', required=True, help='Safe run ID; log is data/study-pilot/<id>.jsonl'
    )
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('schema', help='Return fixture table and column metadata')
    profile = actions.add_parser('profile', help='Return aggregate profile for one column')
    profile.add_argument('table')
    profile.add_argument('column')
    metric = actions.add_parser('metric', help='Run one validated quality metric')
    metric.add_argument('metric_id', choices=sorted(set(METRIC_DIMENSIONS) - {'profile'}))
    metric.add_argument('table')
    metric.add_argument('column')
    metric.add_argument('--parameters', default='{}', help='JSON object of metric parameters')
    sample = actions.add_parser('sample', help='Return redacted shape descriptors')
    sample.add_argument('table')
    sample.add_argument('column')
    sample.add_argument('--limit', type=int, default=10)
    return parser


def main(argv=None, *, output=None):
    args = _parser().parse_args(argv)
    output = sys.stdout if output is None else output
    if not RUN_ID.fullmatch(args.run_id):
        output.write(json.dumps({'status': 'error', 'error': 'Run ID rejected.'}) + '\n')
        return 1
    try:
        if LOG_DIR.is_symlink():
            raise RuntimeError('Run directory rejected')
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / (args.run_id + '.jsonl')
        with _locked_run(path):
            if _action_count(path) >= MAX_ACTIONS:
                output.write(
                    json.dumps({'status': 'error', 'error': 'Run action limit reached.'}) + '\n'
                )
                return 1
            target = None
            summary = {}
            try:
                source = _open_fixture_source()
                try:
                    result, summary = _perform(source, args)
                finally:
                    source.close()
                status = 'completed'
                response = {'status': status, 'action': args.action, 'result': result}
                if args.action != 'schema':
                    target = {'table': args.table, 'column': args.column}
            except Exception:
                status = 'failed'
                response = {'status': 'error', 'error': _GENERIC_ERROR}
            _append_log(
                path,
                {
                    'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    'action': args.action,
                    'target': target,
                    'status': status,
                    'result': summary,
                },
            )
        output.write(json.dumps(response, separators=(',', ':'), allow_nan=False) + '\n')
        return 0 if status == 'completed' else 1
    except Exception:
        output.write(json.dumps({'status': 'error', 'error': _GENERIC_ERROR}) + '\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
