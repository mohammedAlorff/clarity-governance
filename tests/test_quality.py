import unittest

from governance.quality import summarize_results, validate_rule
from governance.source import DemoSource


class RuleValidationTests(unittest.TestCase):
    def setUp(self):
        self.schema = DemoSource().get_schema()

    def test_valid_rule_normalizes_and_does_not_mutate(self):
        rule = {
            'metric_id': 'range',
            'target': {'table': 'orders', 'column': 'amount'},
            'parameters': {'min': 0},
        }
        self.assertEqual(validate_rule(rule, self.schema), rule)

    def test_invalid_unsupported_and_incompatible_rules_are_rejected(self):
        cases = [
            ('sql', 'email', {}),
            ('range', 'email', {'min': 0}),
            ('pattern', 'email', {'pattern': '(a+)+$'}),
            ('allowed_values', 'email', {'values': []}),
            ('completeness', 'email', {'sql': 'DROP TABLE customers'}),
            ('range', 'age', {'min': 10, 'max': 5}),
            ('column_compare', 'age', {'other_column': 'email', 'operator': '>='}),
            ('range', 'age', {'min': float('nan')}),
            ('referential', 'id', {'reference_table': 'orders', 'reference_column': 'missing'}),
        ]
        for metric, column, params in cases:
            with self.subTest(metric=metric, params=params), self.assertRaises(ValueError):
                validate_rule(
                    {
                        'metric_id': metric,
                        'target': {'table': 'customers', 'column': column},
                        'parameters': params,
                    },
                    self.schema,
                )

    def test_requires_plain_identifier_and_known_schema_target(self):
        for column in ('email`', 'email; DROP TABLE customers', 'missing'):
            with self.assertRaises(ValueError):
                validate_rule(
                    {
                        'metric_id': 'completeness',
                        'target': {'table': 'customers', 'column': column},
                    },
                    self.schema,
                )

    def test_allowed_values_types_match_source_column(self):
        for column, values in [('email', [1]), ('age', ['2'])]:
            with self.assertRaises(ValueError):
                validate_rule(
                    {
                        'metric_id': 'allowed_values',
                        'target': {'table': 'customers', 'column': column},
                        'parameters': {'values': values},
                    },
                    self.schema,
                )

    def test_malformed_metric_identifier_has_a_validation_error(self):
        for metric in ([], {}, False, None):
            with self.assertRaises(ValueError):
                validate_rule(
                    {'metric_id': metric, 'target': {'table': 'customers', 'column': 'email'}},
                    self.schema,
                )

    def test_safe_pattern_matcher_preserves_fullmatch_classes_and_bounded_quantifiers(self):
        from governance.quality import matches_pattern

        cases = [
            ('^[A-Z]{2}[0-9]{2}$', 'AB12', True),
            ('^[A-Z]{2}[0-9]{2}$', 'AB123', False),
            ('a?b+', 'bbb', True),
            ('a?b+', 'abb', True),
            ('a?b+', 'aabb', False),
            (r'\d{2,3}', '12', True),
            (r'\d{2,3}', '1', False),
            ('[^@]+@[^@]+', 'a@b', True),
            ('[^@]+@[^@]+', 'a@b@c', False),
        ]
        for pattern, value, expected in cases:
            self.assertEqual(matches_pattern(pattern, value), expected)


class SummaryTests(unittest.TestCase):
    def test_equal_dimension_weighting_with_population_weighted_dimension_scores(self):
        results = [
            dict(dimension='validity', status='completed', eligible=2, passing=0, violations=2),
            dict(dimension='validity', status='completed', eligible=8, passing=8, violations=0),
            dict(dimension='completeness', status='completed', eligible=4, passing=4, violations=0),
        ]
        summary = summarize_results(results)
        self.assertEqual(summary['dimensions']['validity']['score'], 80)
        self.assertEqual(summary['overall_score'], 90)
        self.assertEqual(summary['coverage'], 1)
        self.assertEqual(summary['status'], 'complete')

    def test_unexecuted_and_empty_checks_reduce_coverage_without_fabricated_scores(self):
        results = [
            dict(dimension='validity', status='completed', eligible=10, passing=8),
            dict(dimension='completeness', status='failed', eligible=0, passing=0),
            dict(dimension='uniqueness', status='not_applicable', eligible=0, passing=0),
            dict(dimension='consistency', status='no_eligible_data', eligible=0, passing=0),
        ]
        summary = summarize_results(results)
        self.assertEqual(summary['overall_score'], 80)
        self.assertAlmostEqual(summary['coverage'], 1 / 3)
        self.assertEqual(summary['status'], 'partial')
        self.assertIsNone(summary['dimensions']['completeness']['score'])
        self.assertIsNone(summarize_results([])['overall_score'])
        self.assertEqual(summarize_results([])['status'], 'unavailable')

    def test_profile_never_counts_as_a_quality_check(self):
        result = DemoSource().run_metric('profile', {'table': 'customers', 'column': 'email'}, {})
        summary = summarize_results([result])
        self.assertIsNone(summary['overall_score'])
        self.assertIsNone(summary['coverage'])


if __name__ == '__main__':
    unittest.main()
