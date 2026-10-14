"""Read-only sources. Queries are server-owned templates, never caller SQL."""

import base64
import math
import operator
import os
import re
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from .quality import (
    METRIC_DIMENSIONS,
    identifier,
    matches_pattern,
    mysql_pattern,
    type_family,
    validate_rule,
)
from .sampling import SamplingPolicy, length_bucket

MAX_OUTPUT = 100


def result_policies(metric_id):
    """Return explicit population/null policies for reports, including failures."""
    if metric_id == 'profile':
        population = 'All source rows are profiled; profiles do not contribute to quality scores.'
        nulls = 'NULL values are counted separately and excluded from distinct-value counts.'
    elif metric_id == 'completeness':
        population = 'All source rows are eligible.'
        nulls = 'NULL values are violations; empty strings are present values.'
    elif metric_id == 'column_compare':
        population = 'Rows where both compared columns contain non-NULL values.'
        nulls = (
            'Rows with NULL in either compared column are excluded from the eligible population.'
        )
    elif metric_id == 'referential':
        population = 'Rows whose reference column contains a non-NULL value.'
        nulls = 'NULL source keys are excluded; NULL reference keys never satisfy a match.'
    elif metric_id in METRIC_DIMENSIONS:
        population = 'Rows whose target column contains a non-NULL value.'
        nulls = 'NULL target values are excluded from the eligible population.'
    else:
        raise ValueError('Unsupported metric')
    return {'eligible_population': population, 'null_handling': nulls}


def _json_id(value):
    """Preserve source-key identity while recursively producing strict JSON.

    Bytes use a typed base64 object rather than an undecodable or truncated
    string. Decimal and temporal keys retain exact decimal/ISO representations.
    Composite keys retain their column names and component ordering.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError('Unsupported source primary key value')
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return {
            'type': 'duration',
            'days': value.days,
            'seconds': value.seconds,
            'microseconds': value.microseconds,
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            'type': 'bytes',
            'encoding': 'base64',
            'value': base64.b64encode(bytes(value)).decode('ascii'),
        }
    if isinstance(value, dict):
        return {key: _json_id(component) for key, component in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_id(component) for component in value]
    raise RuntimeError('Unsupported source primary key value')


def _result(rule, eligible, violations, violation_ids):
    return {
        'metric_id': rule['metric_id'],
        'target': rule['target'],
        'dimension': METRIC_DIMENSIONS[rule['metric_id']],
        'status': 'completed' if eligible else 'no_eligible_data',
        'eligible': eligible,
        'passing': eligible - violations,
        'violations': violations,
        'reason': None if eligible else 'No eligible rows',
        'violation_ids': [_json_id(value) for value in violation_ids[:MAX_OUTPUT]],
        **result_policies(rule['metric_id']),
    }


def _shape(value):
    if value is None:
        return {'type': 'null'}
    if isinstance(value, bool):
        return {'type': 'boolean'}
    if isinstance(value, (int, float, Decimal)):
        return {'type': 'number'}
    if isinstance(value, (date, datetime)):
        return {'type': 'date'}
    return {'type': 'string', 'length_bucket': length_bucket(len(str(value)))}


def _sample_limit(limit):
    if type(limit) is not int or not 1 <= limit <= MAX_OUTPUT:
        raise ValueError('Sample limit must be an integer from 1 to 100')


class DemoSource:
    """A deliberately imperfect synthetic shop; rows are not production data."""

    def __init__(self):
        self.closed = False
        self.rows = {
            'customers': [
                {
                    'id': 1,
                    'name': 'Demo One',
                    'email': 'one@example.test',
                    'age': 28,
                    'status': 'active',
                },
                {
                    'id': 2,
                    'name': 'Demo Two',
                    'email': 'shared@example.test',
                    'age': 31,
                    'status': 'active',
                },
                {
                    'id': 3,
                    'name': 'Demo Three',
                    'email': 'shared@example.test',
                    'age': 22,
                    'status': 'inactive',
                },
                {'id': 4, 'name': 'Demo Four', 'email': None, 'age': 45, 'status': 'active'},
                {
                    'id': 5,
                    'name': 'Demo Five',
                    'email': 'invalid-email',
                    'age': -2,
                    'status': 'active',
                },
                {
                    'id': 6,
                    'name': 'Demo Six',
                    'email': 'six@example.test',
                    'age': 37,
                    'status': 'unknown',
                },
                {
                    'id': 7,
                    'name': 'Demo Seven',
                    'email': 'seven@example.test',
                    'age': None,
                    'status': 'inactive',
                },
                {
                    'id': 8,
                    'name': 'Demo Eight',
                    'email': 'eight@example.test',
                    'age': 65,
                    'status': 'active',
                },
            ],
            'orders': [
                {
                    'id': 101,
                    'customer_id': 1,
                    'amount': 50,
                    'ordered_at': '2026-01-01',
                    'shipped_at': '2026-01-02',
                    'status': 'shipped',
                },
                {
                    'id': 102,
                    'customer_id': 2,
                    'amount': -15,
                    'ordered_at': '2026-01-03',
                    'shipped_at': '2026-01-04',
                    'status': 'shipped',
                },
                {
                    'id': 103,
                    'customer_id': 3,
                    'amount': 75,
                    'ordered_at': '2026-01-06',
                    'shipped_at': '2026-01-05',
                    'status': 'shipped',
                },
                {
                    'id': 104,
                    'customer_id': 999,
                    'amount': 30,
                    'ordered_at': '2026-01-07',
                    'shipped_at': '2026-01-08',
                    'status': 'shipped',
                },
                {
                    'id': 105,
                    'customer_id': 5,
                    'amount': 100,
                    'ordered_at': '2026-01-09',
                    'shipped_at': None,
                    'status': 'pending',
                },
                {
                    'id': 106,
                    'customer_id': 8,
                    'amount': 20,
                    'ordered_at': '2026-01-10',
                    'shipped_at': '2026-01-11',
                    'status': 'shipped',
                },
            ],
        }
        self._schema = {
            'name': 'Synthetic shop (demo)',
            'tables': [],
            'relationships': [
                {
                    'table': 'orders',
                    'column': 'customer_id',
                    'reference_table': 'customers',
                    'reference_column': 'id',
                    'declared': True,
                }
            ],
        }
        for table, columns in [
            (
                'customers',
                [
                    ('id', 'int', False, 'PRI'),
                    ('name', 'varchar', False, ''),
                    ('email', 'varchar', True, ''),
                    ('age', 'int', True, ''),
                    ('status', 'varchar', False, ''),
                ],
            ),
            (
                'orders',
                [
                    ('id', 'int', False, 'PRI'),
                    ('customer_id', 'int', False, 'MUL'),
                    ('amount', 'decimal', False, ''),
                    ('ordered_at', 'date', False, ''),
                    ('shipped_at', 'date', True, ''),
                    ('status', 'varchar', False, ''),
                ],
            ),
        ]:
            self._schema['tables'].append(
                {
                    'name': table,
                    'row_count': len(self.rows[table]),
                    'columns': [
                        {'name': n, 'data_type': t, 'nullable': null, 'key': key}
                        for n, t, null, key in columns
                    ],
                }
            )

    def _open(self):
        if self.closed:
            raise RuntimeError('Source is closed')

    def get_schema(self):
        self._open()
        schema = deepcopy(self._schema)
        for table in schema['tables']:
            table['row_count'] = len(self.rows[table['name']])
        return schema

    def snapshot_hash(self):
        """Bind evaluation to every synthetic row value, without exposing values."""
        from .snapshot import SnapshotDigest

        self._open()
        digest = SnapshotDigest()
        for table in sorted(self.rows):
            digest.add_table(table, self.rows[table])
        return digest.hexdigest()

    def run_metric(self, metric_id, target, parameters=None):
        self._open()
        rule = validate_rule(
            {
                'metric_id': metric_id,
                'target': target,
                'parameters': {} if parameters is None else parameters,
            },
            self.get_schema(),
        )
        table, column = rule['target']['table'], rule['target']['column']
        params = rule['parameters']
        rows = self.rows[table]
        values = [r.get(column) for r in rows]
        if metric_id == 'profile':
            result = _result(rule, 0, 0, [])
            result.update(
                status='completed',
                reason='Inspection only',
                row_count=len(values),
                null_count=values.count(None),
                non_null_count=sum(v is not None for v in values),
                distinct_count=len({v for v in values if v is not None}),
            )
            return result
        eligible_rows = (
            rows if metric_id == 'completeness' else [r for r in rows if r.get(column) is not None]
        )
        if metric_id == 'column_compare':
            eligible_rows = [r for r in eligible_rows if r.get(params['other_column']) is not None]
        duplicates = Counter(v for v in values if v is not None)
        references = set()
        if metric_id == 'referential':
            references = {
                r.get(params['reference_column'])
                for r in self.rows[params['reference_table']]
                if r.get(params['reference_column']) is not None
            }
        comparisons = {
            '=': operator.eq,
            '!=': operator.ne,
            '<': operator.lt,
            '<=': operator.le,
            '>': operator.gt,
            '>=': operator.ge,
        }
        failed = []
        for row in eligible_rows:
            value = row.get(column)
            if metric_id == 'completeness':
                passes = value is not None
            elif metric_id == 'uniqueness':
                passes = duplicates[value] == 1
            elif metric_id == 'range':
                passes = ('min' not in params or value >= params['min']) and (
                    'max' not in params or value <= params['max']
                )
            elif metric_id == 'allowed_values':
                passes = value in params['values']
            elif metric_id == 'pattern':
                passes = matches_pattern(params['pattern'], str(value))
            elif metric_id == 'column_compare':
                passes = comparisons[params['operator']](value, row[params['other_column']])
            else:
                passes = value in references
            if not passes:
                failed.append(row.get('id'))
        return _result(rule, len(eligible_rows), len(failed), failed)

    def sample_column(self, table, column, limit=10):
        self._open()
        _sample_limit(limit)
        policy = SamplingPolicy.from_env()
        validate_rule(
            {'metric_id': 'profile', 'target': {'table': table, 'column': column}},
            self.get_schema(),
        )
        candidates = (_shape(r.get(column)) for r in self.rows[table][: policy.candidate_pool])
        samples, sampling = policy.select(candidates, len(self.rows[table]), limit)
        return {
            'table': table,
            'column': column,
            'samples': samples,
            'sample_count': len(samples),
            'redacted': True,
            'sampling': sampling,
        }

    def close(self):
        self.closed = True


class MySQLSource:
    """MySQL adapter requiring a directly granted SELECT-only account.

    Metadata is restricted to MYSQL_DATABASE and optional MYSQL_ALLOWED_TABLES.
    Role-based accounts are rejected because their effective grants cannot be
    safely inferred here. MySQL 5.7+ read-only sessions and timeout hints are used.
    """

    def __init__(self, connection, database, allowed_tables=None, query_timeout_ms=5000):
        self.connection = connection
        self.database = identifier(database)
        self.allowed_tables = set(allowed_tables or [])
        for table in self.allowed_tables:
            identifier(table)
        self.query_timeout_ms = query_timeout_ms
        self.closed = False
        self._schema = None
        try:
            self._configure()
            self._schema = self._load_schema()
        except Exception:
            connection.close()
            self.closed = True
            raise RuntimeError('MySQL read-only connection or schema validation failed') from None

    @classmethod
    def from_env(cls):
        database = os.environ.get('MYSQL_DATABASE', '')
        user = os.environ.get('MYSQL_USER', '')
        if not database or not user:
            raise ValueError('MYSQL_DATABASE and MYSQL_USER are required')
        identifier(database)
        allowed = [
            v.strip() for v in os.environ.get('MYSQL_ALLOWED_TABLES', '').split(',') if v.strip()
        ]
        for table in allowed:
            identifier(table)
        try:
            port = int(os.environ.get('MYSQL_PORT', '3306'))
            timeout_ms = int(os.environ.get('MYSQL_QUERY_TIMEOUT_MS', '5000'))
            connect_timeout = int(os.environ.get('MYSQL_CONNECT_TIMEOUT', '5'))
            if (
                not 1 <= port <= 65535
                or not 100 <= timeout_ms <= 30000
                or not 1 <= connect_timeout <= 30
            ):
                raise ValueError
        except ValueError:
            raise ValueError('Invalid MySQL port or timeout configuration') from None
        try:
            import pymysql
        except ImportError:
            raise RuntimeError('PyMySQL is required for MySQL mode') from None
        tls = {}
        ca = os.environ.get('MYSQL_SSL_CA')
        if ca:
            ssl_options = {'ca': ca}
            for setting, key in [('MYSQL_SSL_CERT', 'cert'), ('MYSQL_SSL_KEY', 'key')]:
                if os.environ.get(setting):
                    ssl_options[key] = os.environ[setting]
            tls = {'ssl': ssl_options, 'ssl_verify_cert': True, 'ssl_verify_identity': True}
        elif os.environ.get('MYSQL_SSL_CERT') or os.environ.get('MYSQL_SSL_KEY'):
            raise ValueError('MYSQL_SSL_CA is required with client TLS certificates')
        try:
            connection = pymysql.connect(
                host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
                port=port,
                user=user,
                password=os.environ.get('MYSQL_PASSWORD', ''),
                database=database,
                connect_timeout=connect_timeout,
                read_timeout=max(1, (timeout_ms + 999) // 1000),
                write_timeout=max(1, (timeout_ms + 999) // 1000),
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
                charset='utf8mb4',
                **tls,
            )
        except Exception:
            raise RuntimeError('MySQL connection failed; check local configuration') from None
        return cls(connection, database, allowed, timeout_ms)

    def _open(self):
        if self.closed:
            raise RuntimeError('Source is closed')

    def _query(self, sql, params=()):
        self._open()
        if sql.lstrip().upper().startswith('SELECT'):
            sql = sql.replace(
                'SELECT', f'SELECT /*+ MAX_EXECUTION_TIME({self.query_timeout_ms}) */', 1
            )
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchmany(MAX_OUTPUT + 1)
                if len(rows) > MAX_OUTPUT:
                    raise RuntimeError('Query output exceeds the safety limit')
                return rows
        except Exception:
            raise RuntimeError('Read-only MySQL query failed or exceeded a limit') from None

    def _configure(self):
        grants = self._query('SHOW GRANTS FOR CURRENT_USER')
        if not grants:
            raise ValueError('Cannot verify source privileges')
        for row in grants:
            grant = str(next(iter(row.values())))
            match = re.match(r'^GRANT (.+?) ON (.+?) TO ', grant, re.I)
            if not match or 'WITH GRANT OPTION' in grant.upper():
                raise ValueError('Cannot verify direct read-only privileges')
            privileges = {p.strip().upper() for p in match.group(1).split(',')}
            if privileges - {'USAGE', 'SELECT', 'SHOW VIEW'}:
                raise ValueError('MySQL account must have only read-only privileges')
            scope = match.group(2).replace('`', '')
            if privileges == {'USAGE'} and scope == '*.*':
                continue
            expected = (
                {self.database + '.' + table for table in self.allowed_tables}
                if self.allowed_tables
                else {self.database + '.*'}
            )
            if scope not in expected:
                raise ValueError(
                    'MySQL grants must be restricted to the permitted source schema/tables'
                )
        self._query('SET SESSION TRANSACTION READ ONLY')
        # MySQL 8 bounds its ICU engine; older supported servers use bounded
        # column lengths and the SELECT execution deadline instead.
        try:
            self._query('SET SESSION regexp_time_limit = 100')
        except RuntimeError:
            pass

    def _load_schema(self):
        columns = self._query(
            "SELECT c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE, c.COLUMN_KEY FROM INFORMATION_SCHEMA.COLUMNS c JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME WHERE c.TABLE_SCHEMA=%s AND t.TABLE_TYPE='BASE TABLE' ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION",
            (self.database,),
        )
        tables = {}
        for row in columns:
            table = row['TABLE_NAME']
            if self.allowed_tables and table not in self.allowed_tables:
                continue
            identifier(table)
            identifier(row['COLUMN_NAME'])
            tables.setdefault(table, {'name': table, 'row_count': 0, 'columns': []})[
                'columns'
            ].append(
                {
                    'name': row['COLUMN_NAME'],
                    'data_type': row['DATA_TYPE'],
                    'nullable': row['IS_NULLABLE'] == 'YES',
                    'key': row['COLUMN_KEY'],
                }
            )
        if self.allowed_tables - set(tables):
            raise ValueError('Allowed tables are missing from the source schema')
        if not tables:
            raise ValueError('No permitted tables available')
        for table in tables.values():
            table['row_count'] = int(
                self._query(f'SELECT COUNT(*) AS count FROM `{self.database}`.`{table["name"]}`')[
                    0
                ]['count']
            )
        relationships = self._query(
            'SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME',
            (self.database, self.database),
        )
        return {
            'name': self.database,
            'tables': list(tables.values()),
            'relationships': [
                {
                    'table': r['TABLE_NAME'],
                    'column': r['COLUMN_NAME'],
                    'reference_table': r['REFERENCED_TABLE_NAME'],
                    'reference_column': r['REFERENCED_COLUMN_NAME'],
                    'declared': True,
                }
                for r in relationships
                if r['TABLE_NAME'] in tables and r['REFERENCED_TABLE_NAME'] in tables
            ],
        }

    def get_schema(self):
        self._open()
        return deepcopy(self._schema)

    def current_schema(self):
        """Re-read metadata for research attestations after a trial."""
        self._open()
        return self._load_schema()

    def begin_evaluation_snapshot(self):
        """Hold one repeatable-read, read-only view across a research run."""
        self._open()
        self._query('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        self._query('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        self._schema = self._load_schema()

    def snapshot_hash(self):
        """Stream selected MySQL base tables with the existing SELECT-only grant."""
        from .snapshot import MAX_ROW_BYTES, MAX_SNAPSHOT_ROWS, SnapshotDigest

        self._open()
        digest = SnapshotDigest()
        try:
            import pymysql

            if sum(table['row_count'] for table in self._schema['tables']) > MAX_SNAPSHOT_ROWS:
                raise RuntimeError('Source snapshot exceeded its row limit.')
            for table in sorted(self._schema['tables'], key=lambda item: item['name']):
                source = self._table(table['name'])
                lengths = '+'.join(
                    f'COALESCE(OCTET_LENGTH(`{column["name"]}`),0)' for column in table['columns']
                )
                maximum = self._query(f'SELECT MAX({lengths}) AS max_bytes FROM {source}')[0][
                    'max_bytes'
                ]
                if maximum is not None and int(maximum) > MAX_ROW_BYTES:
                    raise RuntimeError('A source row exceeded the snapshot size limit.')
                statement = (
                    f'SELECT /*+ MAX_EXECUTION_TIME({self.query_timeout_ms}) */ * FROM {source}'
                )
                cursor = self.connection.cursor(pymysql.cursors.SSDictCursor)
                try:
                    cursor.execute(statement)

                    def rows():
                        while batch := cursor.fetchmany(512):
                            yield from batch

                    digest.add_table(table['name'], rows())
                except Exception:
                    # PyMySQL drains unread streaming rows when its cursor is
                    # closed. Abort the socket instead when a safety bound is
                    # reached; never spend unbounded time draining the query.
                    self.connection.close()
                    self.closed = True
                    raise
                else:
                    cursor.close()
            return digest.hexdigest()
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError('Read-only source snapshot failed.') from None

    def _table(self, table):
        return f'`{self.database}`.`{identifier(table)}`'

    def run_metric(self, metric_id, target, parameters=None):
        rule = validate_rule(
            {
                'metric_id': metric_id,
                'target': target,
                'parameters': {} if parameters is None else parameters,
            },
            self.get_schema(),
        )
        table, column = target['table'], target['column']
        params = rule['parameters']
        source = self._table(table)
        col = f't.`{column}`'
        if metric_id == 'profile':
            data = self._query(
                f'SELECT COUNT(*) AS row_count, COUNT({col}) AS non_null_count, COUNT(*)-COUNT({col}) AS null_count, COUNT(DISTINCT {col}) AS distinct_count FROM {source} t'
            )[0]
            result = _result(rule, 0, 0, [])
            result.update({key: int(value) for key, value in data.items()})
            result.update(status='completed', reason='Inspection only')
            return result
        eligible = '1=1' if metric_id == 'completeness' else f'{col} IS NOT NULL'
        arguments = []
        if metric_id == 'completeness':
            failure = f'{col} IS NULL'
        elif metric_id == 'uniqueness':
            failure = f'{col} IN (SELECT d.`{column}` FROM {source} d WHERE d.`{column}` IS NOT NULL GROUP BY d.`{column}` HAVING COUNT(*)>1)'
        elif metric_id == 'range':
            clauses = []
            for bound, comparison in [('min', '<'), ('max', '>')]:
                if bound in params:
                    clauses.append(f'{col} {comparison} %s')
                    arguments.append(params[bound])
            failure = '(' + ' OR '.join(clauses) + ')'
        elif metric_id == 'allowed_values':
            failure = f'{col} NOT IN (' + ','.join(['%s'] * len(params['values'])) + ')'
            arguments.extend(params['values'])
        elif metric_id == 'pattern':
            # Explicit binary collation ensures case-sensitive matching.
            text = f'CAST({col} AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_bin'
            failure = f'(CHAR_LENGTH({col})>512 OR NOT ({text} REGEXP %s))'
            arguments.append(mysql_pattern(params['pattern']))
        elif metric_id == 'column_compare':
            other = f't.`{params["other_column"]}`'
            eligible += f' AND {other} IS NOT NULL'
            failure = f'NOT ({col} {params["operator"]} {other})'
        else:
            reference = self._table(params['reference_table'])
            failure = f'NOT EXISTS (SELECT 1 FROM {reference} r WHERE r.`{params["reference_column"]}`={col})'
        counts = self._query(
            f'SELECT COUNT(*) AS eligible, COALESCE(SUM(CASE WHEN {failure} THEN 1 ELSE 0 END),0) AS violations FROM {source} t WHERE {eligible}',
            tuple(arguments),
        )[0]
        count = int(counts['violations'])
        ids = []
        keys = [
            c['name']
            for t in self._schema['tables']
            if t['name'] == table
            for c in t['columns']
            if c['key'] == 'PRI'
        ]
        if keys and count:
            # Composite key components are returned as an identifier object.
            selection = ','.join(f't.`{key}`' for key in keys)
            fetched = self._query(
                f'SELECT {selection} FROM {source} t WHERE {eligible} AND {failure} ORDER BY {selection} LIMIT {MAX_OUTPUT}',
                tuple(arguments),
            )
            ids = [r[keys[0]] if len(keys) == 1 else r for r in fetched]
        return _result(rule, int(counts['eligible']), count, ids)

    def sample_column(self, table, column, limit=10):
        _sample_limit(limit)
        policy = SamplingPolicy.from_env()
        validate_rule(
            {'metric_id': 'profile', 'target': {'table': table, 'column': column}},
            self.get_schema(),
        )
        table_info = next(t for t in self._schema['tables'] if t['name'] == table)
        info = next(c for c in table_info['columns'] if c['name'] == column)
        family = type_family(info['data_type'])
        keys = [c['name'] for c in table_info['columns'] if c['key'] == 'PRI']
        ordering = ' ORDER BY ' + ','.join(f'`{key}`' for key in keys) if keys else ''
        # Fetch only null/length descriptors. Primary keys order the bounded
        # pool but are never selected or included in the sampling response.
        rows = self._query(
            f'SELECT (`{column}` IS NULL) AS is_null, CHAR_LENGTH(CAST(`{column}` AS CHAR)) AS length FROM {self._table(table)}{ordering} LIMIT {policy.candidate_pool}'
        )
        candidates = (
            {'type': 'null'}
            if row['is_null']
            else {
                'type': family,
                **(
                    {'length_bucket': length_bucket(int(row['length']))}
                    if family == 'string'
                    else {}
                ),
            }
            for row in rows
        )
        samples, sampling = policy.select(candidates, table_info['row_count'], limit)
        return {
            'table': table,
            'column': column,
            'samples': samples,
            'sample_count': len(samples),
            'redacted': True,
            'sampling': sampling,
        }

    def close(self):
        if not self.closed:
            self.connection.close()
            self.closed = True
