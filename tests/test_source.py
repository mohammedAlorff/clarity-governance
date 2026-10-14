import json
import unittest
from unittest.mock import patch

from governance.source import DemoSource, MySQLSource


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.source = DemoSource()

    def test_duplicate_groups_include_all_members_and_exclude_nulls(self):
        result = self.source.run_metric('uniqueness', {'table': 'customers', 'column': 'email'}, {})
        self.assertEqual((result['eligible'], result['passing'], result['violations']), (7, 5, 2))
        self.assertEqual(result['violation_ids'], [2, 3])

    def test_metrics_are_read_only_and_all_dimensions_have_real_failures(self):
        before = json.dumps(self.source.rows, sort_keys=True)
        cases = [
            ('completeness', 'customers', 'email', {}, 8, 1),
            ('range', 'orders', 'amount', {'min': 0}, 6, 1),
            ('allowed_values', 'customers', 'status', {'values': ['active', 'inactive']}, 8, 1),
            ('pattern', 'customers', 'email', {'pattern': r'^[^@\s]+@[^@\s]+\.[^@\s]+$'}, 7, 1),
            (
                'column_compare',
                'orders',
                'shipped_at',
                {'other_column': 'ordered_at', 'operator': '>='},
                5,
                1,
            ),
            (
                'referential',
                'orders',
                'customer_id',
                {'reference_table': 'customers', 'reference_column': 'id'},
                6,
                1,
            ),
        ]
        for metric, table, column, params, eligible, violations in cases:
            with self.subTest(metric=metric):
                result = self.source.run_metric(metric, {'table': table, 'column': column}, params)
                self.assertEqual(result['status'], 'completed')
                self.assertEqual(result['eligible'], eligible)
                self.assertEqual(result['violations'], violations)
        self.assertEqual(json.dumps(self.source.rows, sort_keys=True), before)

    def test_profiles_and_samples_never_expose_raw_values(self):
        self.source.rows['customers'][0]['email'] = 'SECRET_CANARY@example.invalid'
        profile = self.source.run_metric('profile', {'table': 'customers', 'column': 'email'}, {})
        self.assertEqual(
            (profile['row_count'], profile['null_count'], profile['non_null_count']), (8, 1, 7)
        )
        samples = self.source.sample_column('customers', 'email', 8)
        self.assertTrue(samples['redacted'])
        self.assertEqual(samples['sample_count'], 1)
        encoded = json.dumps([profile, samples])
        self.assertNotIn('SECRET_CANARY', encoded)
        self.assertNotIn('example.invalid', encoded)
        self.assertNotIn('min', profile)
        self.assertNotIn('max', profile)

    def test_empty_population_cannot_pass(self):
        self.source.rows['customers'] = []
        result = self.source.run_metric(
            'completeness', {'table': 'customers', 'column': 'email'}, {}
        )
        self.assertEqual(result['status'], 'no_eligible_data')
        self.assertEqual(result['passing'], 0)

    def test_null_population_excluded_from_non_completeness_checks(self):
        for row in self.source.rows['customers']:
            row['email'] = None
        result = self.source.run_metric('uniqueness', {'table': 'customers', 'column': 'email'}, {})
        self.assertEqual(result['status'], 'no_eligible_data')
        self.assertEqual(result['eligible'], 0)

    def test_violation_output_is_bounded_but_total_count_is_accurate(self):
        self.source.rows['customers'] = [{'id': i, 'email': None} for i in range(500)]
        result = self.source.run_metric(
            'completeness', {'table': 'customers', 'column': 'email'}, {}
        )
        self.assertEqual(result['violations'], 500)
        self.assertLessEqual(len(result['violation_ids']), 100)

    def test_samples_limits_and_closed_sources_reject_calls(self):
        for limit in (0, 101, -1, '10', True):
            with self.assertRaises(ValueError):
                self.source.sample_column('customers', 'email', limit)
        self.source.close()
        with self.assertRaises(RuntimeError):
            self.source.get_schema()

    def test_schema_is_detached_from_source(self):
        schema = self.source.get_schema()
        schema['tables'][0]['columns'][0]['name'] = 'tampered'
        self.assertEqual(self.source.get_schema()['tables'][0]['columns'][0]['name'], 'id')

    def test_pattern_repeated_tokens_have_bounded_matching_without_backtracking(self):
        import subprocess
        import sys

        code = "from governance.source import DemoSource; s=DemoSource(); s.rows['customers'][0]['email']='a'*500; r=s.run_metric('pattern',{'table':'customers','column':'email'},{'pattern':'a*a*a*a*a*a*a*b'}); assert r['violations']==7"
        completed = subprocess.run([sys.executable, '-c', code], timeout=3, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())


class MySQLConfigurationTests(unittest.TestCase):
    def test_missing_database_config_fails_without_import_or_network(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            MySQLSource.from_env()

    def test_invalid_database_identifier_is_rejected_before_connect(self):
        config = {'MYSQL_DATABASE': 'shop;DROP', 'MYSQL_USER': 'reader', 'MYSQL_PASSWORD': 'canary'}
        with patch.dict('os.environ', config, clear=True), self.assertRaises(ValueError):
            MySQLSource.from_env()

    def test_optional_tls_requires_certificate_verification(self):
        import types

        captured = {}

        def connect(**kwargs):
            captured.update(kwargs)
            return FakeConnection()

        driver = types.SimpleNamespace(
            connect=connect, cursors=types.SimpleNamespace(DictCursor=object)
        )
        config = {'MYSQL_DATABASE': 'shop', 'MYSQL_USER': 'reader', 'MYSQL_SSL_CA': 'ca.pem'}
        with (
            patch.dict('os.environ', config, clear=True),
            patch.dict('sys.modules', {'pymysql': driver}),
        ):
            source = MySQLSource.from_env()
        self.assertEqual(captured['ssl']['ca'], 'ca.pem')
        self.assertTrue(captured['ssl_verify_cert'])
        self.assertTrue(captured['ssl_verify_identity'])
        source.close()


class FakeCursor:
    """Only the external driver boundary is replaced; SQL construction is real."""

    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params):
        self.connection.queries.append((sql, params))
        if sql.startswith('SHOW GRANTS'):
            self.rows = [{'grant': self.connection.grant}]
        elif 'INFORMATION_SCHEMA.COLUMNS' in sql:
            self.rows = self.connection.columns
        elif 'INFORMATION_SCHEMA.KEY_COLUMN_USAGE' in sql:
            self.rows = []
        elif 'COUNT(*) AS count' in sql:
            self.rows = [{'count': 8}]
        elif 'AS eligible' in sql:
            self.rows = [{'eligible': 7, 'violations': 2}]
        elif 'SELECT /*' in sql and 't.`id`' in sql:
            self.rows = self.connection.id_rows
        else:
            self.rows = []

    def fetchmany(self, limit):
        return self.rows[:limit]


class FakeConnection:
    def __init__(self, grant='GRANT SELECT ON `shop`.* TO `reader`@`localhost`'):
        self.grant = grant
        self.queries = []
        self.closed = False
        self.columns = [
            {
                'TABLE_NAME': 'customers',
                'COLUMN_NAME': 'id',
                'DATA_TYPE': 'int',
                'IS_NULLABLE': 'NO',
                'COLUMN_KEY': 'PRI',
            },
            {
                'TABLE_NAME': 'customers',
                'COLUMN_NAME': 'email',
                'DATA_TYPE': 'varchar',
                'IS_NULLABLE': 'YES',
                'COLUMN_KEY': '',
            },
        ]
        self.id_rows = [{'id': 2}, {'id': 3}]

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class MySQLTemplateTests(unittest.TestCase):
    def test_binary_primary_keys_serialize_without_colliding_with_text_keys(self):
        connection = FakeConnection()
        connection.id_rows = [{'id': b'\x00\xff'}, {'id': 'AP8='}]
        source = MySQLSource(connection, 'shop')
        result = source.run_metric('uniqueness', {'table': 'customers', 'column': 'email'}, {})
        encoded = json.dumps(result, allow_nan=False)
        restored = json.loads(encoded)
        self.assertEqual(
            restored['violation_ids'][0], {'type': 'bytes', 'encoding': 'base64', 'value': 'AP8='}
        )
        self.assertEqual(restored['violation_ids'][1], 'AP8=')
        self.assertNotEqual(restored['violation_ids'][0], restored['violation_ids'][1])

    def test_composite_primary_key_components_are_recursively_json_safe_and_stable(self):
        from datetime import date, datetime
        from decimal import Decimal

        connection = FakeConnection()
        for name, kind in [
            ('created_at', 'datetime'),
            ('fraction', 'decimal'),
            ('binary_part', 'binary'),
        ]:
            connection.columns.append(
                {
                    'TABLE_NAME': 'customers',
                    'COLUMN_NAME': name,
                    'DATA_TYPE': kind,
                    'IS_NULLABLE': 'NO',
                    'COLUMN_KEY': 'PRI',
                }
            )
        connection.id_rows = [
            {
                'id': date(2026, 9, 27),
                'created_at': datetime(2026, 9, 27, 9, 10, 11),
                'fraction': Decimal('12.3400'),
                'binary_part': b'\x00\xff',
            }
        ]
        source = MySQLSource(connection, 'shop')
        result = source.run_metric('uniqueness', {'table': 'customers', 'column': 'email'}, {})
        restored = json.loads(json.dumps(result, allow_nan=False))
        self.assertEqual(
            restored['violation_ids'],
            [
                {
                    'id': '2026-09-27',
                    'created_at': '2026-09-27T09:10:11',
                    'fraction': '12.3400',
                    'binary_part': {'type': 'bytes', 'encoding': 'base64', 'value': 'AP8='},
                }
            ],
        )

    def test_scalar_decimal_and_temporal_primary_keys_are_json_safe(self):
        from datetime import date, datetime
        from decimal import Decimal

        connection = FakeConnection()
        connection.id_rows = [
            {'id': Decimal('123.4500')},
            {'id': datetime(2026, 9, 27, 9, 10, 11)},
            {'id': date(2026, 9, 27)},
        ]
        source = MySQLSource(connection, 'shop')
        result = source.run_metric('uniqueness', {'table': 'customers', 'column': 'email'}, {})
        restored = json.loads(json.dumps(result, allow_nan=False))
        self.assertEqual(
            restored['violation_ids'], ['123.4500', '2026-09-27T09:10:11', '2026-09-27']
        )

    def test_all_metric_results_explain_population_and_null_handling(self):
        source = DemoSource()
        cases = [
            ('profile', 'customers', 'email', {}),
            ('completeness', 'customers', 'email', {}),
            ('uniqueness', 'customers', 'email', {}),
            ('range', 'orders', 'amount', {'min': 0}),
            ('allowed_values', 'customers', 'status', {'values': ['active', 'inactive']}),
            ('pattern', 'customers', 'email', {'pattern': r'[^@]+@[^@]+'}),
            (
                'column_compare',
                'orders',
                'shipped_at',
                {'other_column': 'ordered_at', 'operator': '>='},
            ),
            (
                'referential',
                'orders',
                'customer_id',
                {'reference_table': 'customers', 'reference_column': 'id'},
            ),
        ]
        for metric, table, column, parameters in cases:
            with self.subTest(metric=metric):
                result = source.run_metric(metric, {'table': table, 'column': column}, parameters)
                self.assertIsInstance(result['eligible_population'], str)
                self.assertIsInstance(result['null_handling'], str)
                self.assertGreater(len(result['eligible_population']), 10)
                self.assertGreater(len(result['null_handling']), 10)
        completeness = source.run_metric(
            'completeness', {'table': 'customers', 'column': 'email'}, {}
        )
        self.assertIn('violations', completeness['null_handling'])
        comparison = source.run_metric(
            'column_compare',
            {'table': 'orders', 'column': 'shipped_at'},
            {'other_column': 'ordered_at', 'operator': '>='},
        )
        self.assertIn('both', comparison['eligible_population'])

    def test_select_grants_outside_selected_schema_are_rejected(self):
        for scope in ('*.*', '`other`.*', '`shop`.`unlisted`'):
            with self.subTest(scope=scope), self.assertRaises(RuntimeError):
                MySQLSource(
                    FakeConnection(f'GRANT SELECT ON {scope} TO `reader`@`localhost`'),
                    'shop',
                    ['customers'],
                )

    def test_write_privilege_account_is_rejected_and_closed(self):
        connection = FakeConnection('GRANT SELECT, INSERT ON `shop`.* TO `reader`@`localhost`')
        with self.assertRaises(RuntimeError):
            MySQLSource(connection, 'shop')
        self.assertTrue(connection.closed)

    def test_role_account_is_rejected_when_effective_grants_cannot_be_verified(self):
        with self.assertRaises(RuntimeError):
            MySQLSource(FakeConnection('GRANT `writer`@`%` TO `reader`@`localhost`'), 'shop')

    def test_metric_count_and_ids_use_parameters_and_only_owned_templates(self):
        connection = FakeConnection()
        source = MySQLSource(connection, 'shop')
        result = source.run_metric(
            'allowed_values',
            {'table': 'customers', 'column': 'email'},
            {'values': ["x'); DROP TABLE customers; --"]},
        )
        self.assertEqual(
            (result['eligible'], result['violations'], result['violation_ids']), (7, 2, [2, 3])
        )
        sql, parameters = connection.queries[-2]
        self.assertIn('MAX_EXECUTION_TIME(5000)', sql)
        self.assertNotIn('DROP TABLE', sql)
        self.assertEqual(parameters, ("x'); DROP TABLE customers; --",))
        self.assertTrue(
            any(sql == 'SET SESSION TRANSACTION READ ONLY' for sql, _ in connection.queries)
        )

    def test_invalid_identifiers_never_reach_the_driver(self):
        connection = FakeConnection()
        source = MySQLSource(connection, 'shop')
        count = len(connection.queries)
        with self.assertRaises(ValueError):
            source.run_metric('profile', {'table': 'customers;DROP', 'column': 'email'}, {})
        self.assertEqual(len(connection.queries), count)

    def test_driver_errors_are_safe_and_do_not_leak_credentials(self):
        class FailingCursor(FakeCursor):
            def execute(self, sql, params):
                raise RuntimeError('SECRET_CANARY password and source value')

        connection = FakeConnection()
        source = MySQLSource(connection, 'shop')
        connection.cursor = lambda: FailingCursor(connection)
        with self.assertRaises(RuntimeError) as context:
            source.run_metric('profile', {'table': 'customers', 'column': 'email'}, {})
        self.assertNotIn('SECRET_CANARY', str(context.exception))

    def test_false_non_object_parameters_are_rejected(self):
        source = DemoSource()
        for parameters in ([], False, 0, ''):
            with self.assertRaises(ValueError):
                source.run_metric('profile', {'table': 'customers', 'column': 'email'}, parameters)


if __name__ == '__main__':
    unittest.main()
