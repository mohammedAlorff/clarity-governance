import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class QualityTests(unittest.TestCase):
    def test_duplicate_group_and_null_population(self):
        from governance.source import DemoSource

        source = DemoSource()
        result = source.run_metric('uniqueness', {'table': 'customers', 'column': 'email'}, {})
        self.assertEqual(result['violations'], 2)
        self.assertEqual(result['eligible'], 7)
        self.assertEqual(len(result['violation_ids']), 2)

    def test_scoring_empty_failed_and_inapplicable(self):
        from governance.quality import summarize_results

        results = [
            dict(dimension='validity', status='completed', eligible=10, passing=8),
            dict(dimension='completeness', status='failed', eligible=0, passing=0),
            dict(dimension='uniqueness', status='not_applicable', eligible=0, passing=0),
        ]
        score = summarize_results(results)
        self.assertEqual(score['overall_score'], 80)
        self.assertEqual(score['coverage'], 0.5)
        self.assertEqual(score['status'], 'partial')
        self.assertIsNone(summarize_results([])['overall_score'])

    def test_invalid_target_and_metric_are_rejected(self):
        from governance.source import DemoSource

        s = DemoSource()
        for metric, target in [
            ('sql', {'table': 'customers', 'column': 'email'}),
            ('profile', {'table': 'customers; DROP', 'column': 'email'}),
        ]:
            with self.assertRaises(ValueError):
                s.run_metric(metric, target, {})

    def test_all_four_dimensions_and_no_source_mutation(self):
        from governance.source import DemoSource

        s = DemoSource()
        before = json.dumps(s.rows, sort_keys=True)
        cases = [
            ('completeness', 'customers', 'email', {}),
            ('range', 'orders', 'amount', {'min': 0}),
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
        for metric, table, column, params in cases:
            result = s.run_metric(metric, {'table': table, 'column': column}, params)
            self.assertEqual(result['status'], 'completed')
            self.assertGreater(result['violations'], 0)
        self.assertEqual(before, json.dumps(s.rows, sort_keys=True))


class StoreTests(unittest.TestCase):
    def test_review_versions_are_immutable_and_rejected_cannot_approve(self):
        from governance.store import Conflict, Store

        with TemporaryDirectory() as directory:
            s = Store(Path(directory) / 'state.db')
            scope = s.new_scope('demo', 'test')
            p = s.add_proposal(
                scope,
                {
                    'kind': 'description',
                    'target': {'table': 't', 'column': 'c'},
                    'title': 'A',
                    'description': 'original',
                    'evidence': ['observed'],
                    'assumptions': [],
                    'status': 'draft',
                    'rule': None,
                },
            )
            s.review(p['id'], 'reject', 'analyst', 'unsupported')
            with self.assertRaises(Conflict):
                s.review(p['id'], 'approve', 'analyst', '')
            edited = s.review(p['id'], 'edit', 'analyst', '', {'description': 'corrected'})
            self.assertEqual(edited['status'], 'draft')
            self.assertEqual(edited['version'], 2)
            self.assertEqual(edited['original']['description'], 'original')
            self.assertEqual(s.get_proposal(p['id'])['status'], 'rejected')
            s.review(edited['id'], 'approve', 'analyst', '')
            self.assertEqual(len(s.approved_rules(scope)), 0)


class AgentTests(unittest.TestCase):
    def test_canaries_never_reach_model_or_trace(self):
        from governance.privacy import model_view

        value = {
            'comment': 'SECRET_CANARY',
            'samples': ['SECRET_CANARY'],
            'error': 'SECRET_CANARY',
            'eligible': 2,
        }
        self.assertNotIn('SECRET_CANARY', json.dumps(model_view(value)))
        self.assertEqual(model_view(value)['eligible'], 2)

    def test_unsupported_tool_is_blocked_and_loop_is_bounded(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits
        from governance.source import DemoSource

        class Client:
            model = 'test'
            provider = 'test'

            def respond(self, messages, tools, max_tokens, timeout):
                return {
                    'calls': [
                        {'name': 'execute_sql', 'arguments': {'sql': 'DROP TABLE customers'}}
                    ],
                    'proposals': [],
                    'usage': {'input_tokens': 1, 'output_tokens': 1},
                }

        result = run_inspection(
            DemoSource(), Client(), 'agent', RunLimits(max_calls=2, max_steps=2)
        )
        self.assertLessEqual(len(result['trace']), 2)
        self.assertNotEqual(result['status'], 'completed')
        self.assertIn('blocked', json.dumps(result['trace']))


class EvaluationTests(unittest.TestCase):
    def test_dedup_and_zero_denominators(self):
        from governance.evaluation import detection_metrics

        alert = {'rule_id': 'r', 'row_id': '1', 'target': 't.c'}
        self.assertEqual(detection_metrics([alert, alert], [alert])['tp'], 1)
        self.assertEqual(detection_metrics([alert], [alert])['f1'], 1)
        self.assertIsNone(detection_metrics([], [])['precision'])
        self.assertIsNone(detection_metrics([], [])['recall'])


if __name__ == '__main__':
    unittest.main()
