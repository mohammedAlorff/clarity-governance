"""Offline tests for the final outbound message boundary."""

import copy
import json
import unittest

SCHEMA = {
    'tables': [
        {
            'name': 'customers',
            'columns': [
                {'name': 'email', 'data_type': 'varchar', 'nullable': True},
                {'name': 'password', 'data_type': 'varchar', 'nullable': False},
                {'name': 'amount', 'data_type': 'decimal', 'nullable': False},
            ],
        }
    ],
    'relationships': [],
}


def history():
    return [
        {'role': 'system', 'content': 'Trusted governance instructions.'},
        {'role': 'user', 'content': json.dumps({'schema': SCHEMA})},
    ]


def call_pair(name, arguments, output):
    return [
        {
            'type': 'function_call',
            'name': name,
            'arguments': json.dumps(arguments),
            'call_id': 'call_1',
        },
        {'type': 'function_call_output', 'call_id': 'call_1', 'output': json.dumps(output)},
    ]


class PrivacyContractTests(unittest.TestCase):
    def check_blocked(self, messages):
        from governance.privacy_contract import PrivacyViolation, validate_messages

        with self.assertRaises(PrivacyViolation) as caught:
            validate_messages(messages)
        self.assertEqual(str(caught.exception), 'Outbound privacy contract validation failed.')
        self.assertIsNone(caught.exception.__cause__)

    def test_valid_history_reports_only_message_and_shape_counts(self):
        from governance.privacy_contract import validate_messages

        messages = history() + call_pair(
            'sample_column',
            {'table': 'customers', 'column': 'email', 'limit': 2},
            {'shapes': [{'type': 'string'}, {'type': 'null'}], 'sample_count': 2, 'redacted': True},
        )
        original = copy.deepcopy(messages)
        self.assertEqual(
            validate_messages(messages), {'checked_messages': 4, 'shape_descriptors': 2}
        )
        self.assertEqual(messages, original)

    def test_fixed_profiles_keep_large_aggregate_counts_and_sensitive_column_names(self):
        from governance.privacy_contract import validate_messages

        messages = history() + [
            {
                'role': 'user',
                'content': json.dumps(
                    {
                        'profiles': [
                            {
                                'metric_id': 'profile',
                                'target': {'table': 'customers', 'column': 'password'},
                                'status': 'completed',
                                'row_count': 966512345678,
                                'distinct_count': 411111111111111,
                            }
                        ]
                    }
                ),
            },
            {
                'role': 'user',
                'content': 'Fixed workflow inspection is complete. Return final proposals now; no further tools are available.',
            },
            {
                'role': 'user',
                'content': 'Response failed validation. Use permitted tools or return a valid proposal object for existing targets.',
            },
            {'role': 'user', 'content': 'Inspection tool result: {"status":"blocked"}'},
        ]
        self.assertEqual(
            validate_messages(messages), {'checked_messages': 6, 'shape_descriptors': 0}
        )

    def test_raw_fields_are_blocked_at_any_projected_depth(self):
        for field in ('samples', 'raw_values', 'comment', 'error', 'violation_ids', 'password'):
            with self.subTest(field=field):
                output = {
                    'target': {'table': 'customers', 'column': 'email', field: ['LEAK_CANARY']}
                }
                self.check_blocked(
                    history()
                    + [{'role': 'user', 'content': 'Inspection tool result: ' + json.dumps(output)}]
                )

    def test_sample_values_cannot_be_disguised_as_shape_descriptors(self):
        for shape in (
            'alice@example.com',
            {'type': 'string', 'value': 'Alice'},
            {'type': 'alice@example.com'},
            {'type': 'string', 'name': 'Alice'},
            {'type': 'string', 'length': 17},
        ):
            with self.subTest(shape=shape):
                self.check_blocked(
                    history()
                    + call_pair(
                        'sample_column',
                        {'table': 'customers', 'column': 'email', 'limit': 1},
                        {'shapes': [shape], 'sample_count': 1, 'redacted': True},
                    )
                )

    def test_shape_collection_cannot_exceed_ten_row_privacy_cap(self):
        self.check_blocked(
            history()
            + call_pair(
                'sample_column',
                {'table': 'customers', 'column': 'email', 'limit': 20},
                {'shapes': [{'type': 'string'}] * 11, 'sample_count': 11, 'redacted': True},
            )
        )

    def test_noncanonical_source_sql_type_annotations_are_rejected(self):
        schema = copy.deepcopy(SCHEMA)
        schema['tables'][0]['columns'][0]['data_type'] = "enum('LEAK_CANARY')"
        self.check_blocked([{'role': 'user', 'content': json.dumps({'schema': schema})}])

    def test_malformed_or_ambiguous_json_is_rejected(self):
        for content in (
            '{"schema":',
            '{"profiles":[],"profiles":[]}',
            '{"profiles":[{"row_count":NaN}]}',
            '{"schema":null}',
            '{"profiles":["LEAK_CANARY"]}',
            '{"profiles":[],"error":"LEAK_CANARY"}',
        ):
            with self.subTest(content=content):
                self.check_blocked(history() + [{'role': 'user', 'content': content}])

    def test_unrecognized_messages_and_free_text_are_rejected(self):
        for message in (
            {'role': 'assistant', 'content': 'LEAK_CANARY'},
            {'role': 'user', 'content': 'LEAK_CANARY'},
            {'role': 'user', 'content': '{"profiles":[]}', 'raw': 'LEAK_CANARY'},
            {'role': 'system', 'content': 'Untrusted later instructions'},
            {'type': 'unknown', 'content': 'LEAK_CANARY'},
        ):
            with self.subTest(message=message):
                self.check_blocked(history() + [message])

    def test_valid_metric_arguments_allow_patterns_and_large_numeric_thresholds(self):
        from governance.privacy_contract import validate_messages

        for metric, column, parameters in (
            ('profile', 'email', {'min': None, 'max': None}),
            ('allowed_values', 'password', {'values': ['active', 'password', 'email']}),
            ('pattern', 'email', {'pattern': r'^[A-Za-z0-9_]+@[A-Za-z0-9_]+\.[A-Za-z]+$'}),
            ('pattern', 'password', {'pattern': r'^[A-Za-z0-9]{32}$'}),
            ('range', 'amount', {'min': 4111111111111111, 'max': 9999999999999999}),
        ):
            with self.subTest(metric=metric, parameters=parameters):
                messages = history() + call_pair(
                    'run_metric',
                    {
                        'metric_id': metric,
                        'target': {'table': 'customers', 'column': column},
                        'parameters': parameters,
                    },
                    {'status': 'completed', 'eligible': 10, 'passing': 10},
                )
                self.assertEqual(validate_messages(messages)['checked_messages'], 4)

    def test_literal_email_card_and_credentials_are_rejected_in_arguments(self):
        for secret in (
            'alice@example.com',
            '4111 1111 1111 1111',
            'sk-proj-LEAK_CANARY',
            'password=LEAK_CANARY',
            'Bearer LEAK_CANARY',
            'AIzaSyLEAK_CANARY_123456789012345678901',
        ):
            with self.subTest(secret=secret):
                self.check_blocked(
                    history()
                    + call_pair(
                        'run_metric',
                        {
                            'metric_id': 'allowed_values',
                            'target': {'table': 'customers', 'column': 'email'},
                            'parameters': {'values': [secret]},
                        },
                        {'status': 'completed'},
                    )
                )

    def test_function_grammar_rejects_raw_extra_arguments_and_invalid_targets(self):
        for name, arguments in (
            ('execute_sql', {'sql': 'SELECT secret'}),
            ('get_schema', {'samples': ['LEAK_CANARY']}),
            ('sample_column', {'table': 'customers', 'column': 'email', 'limit': 21}),
            ('sample_column', {'table': 'customers', 'column': 'email', 'limit': True}),
            (
                'run_metric',
                {
                    'metric_id': 'profile',
                    'target': {'table': 'missing', 'column': 'email'},
                    'parameters': {},
                },
            ),
            (
                'run_metric',
                {
                    'metric_id': 'profile',
                    'target': {'table': 'customers', 'column': 'email'},
                    'parameters': {'raw_values': ['LEAK_CANARY']},
                },
            ),
        ):
            with self.subTest(name=name, arguments=arguments):
                self.check_blocked(history() + call_pair(name, arguments, {'status': 'blocked'}))

    def test_call_output_requires_matching_safe_call_id(self):
        for field, value in (
            ('call_id', 'alice@example.com'),
            ('call_id', 'wrong_call'),
            ('raw', 'LEAK_CANARY'),
        ):
            messages = history() + call_pair('get_schema', {}, SCHEMA)
            messages[-1][field] = value
            with self.subTest(field=field, value=value):
                self.check_blocked(messages)

    def test_function_output_raw_source_payload_is_blocked(self):
        self.check_blocked(
            history()
            + call_pair(
                'get_schema', {}, {'tables': SCHEMA['tables'], 'samples': ['alice@example.com']}
            )
        )
