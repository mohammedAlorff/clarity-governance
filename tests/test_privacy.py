import json
import unittest


class PrivacyTests(unittest.TestCase):
    def test_raw_fields_and_unknown_nested_payloads_are_withheld(self):
        from governance.privacy import model_view

        payload = {
            'eligible': 9,
            'nested': {'comment': 'CANARY'},
            'samples': ['CANARY'],
            'error': 'CANARY',
            'raw_values': ['CANARY'],
            'reason': 'CANARY',
            'violation_ids': ['CANARY'],
            'password': 'CANARY',
        }
        view = model_view(payload)
        self.assertEqual(view['eligible'], 9)
        self.assertNotIn('CANARY', json.dumps(view))

    def test_schema_and_aggregate_counts_survive_without_comments(self):
        from governance.privacy import model_view

        view = model_view(
            {
                'tables': [
                    {
                        'name': 'orders',
                        'columns': [
                            {
                                'name': 'amount',
                                'data_type': 'decimal',
                                'nullable': False,
                                'comment': 'CANARY',
                            }
                        ],
                    }
                ],
                'null_count': 3,
                'distinct_count': 8,
            }
        )
        self.assertEqual(view['tables'][0]['columns'][0]['name'], 'amount')
        self.assertEqual(view['null_count'], 3)
        self.assertNotIn('CANARY', json.dumps(view))

    def test_unbounded_outputs_are_truncated(self):
        from governance.privacy import model_view

        self.assertLessEqual(len(model_view({'tables': [{'name': 't'}] * 1000})['tables']), 100)

    def test_total_projection_size_is_bounded_across_nested_containers(self):
        from governance.privacy import model_view

        payload = {
            'tables': [{'name': 't', 'columns': [{'name': 'c', 'data_type': 'varchar'}] * 100}]
            * 100
        }
        self.assertLess(len(json.dumps(model_view(payload))), 100000)
