import pytest

from scripts.study_score import score_trial


class TinySource:
    def get_schema(self):
        return {
            'tables': [
                {
                    'name': 'actor',
                    'row_count': 2,
                    'columns': [
                        {
                            'name': 'first_name',
                            'data_type': 'varchar(45)',
                            'nullable': True,
                            'key': '',
                        }
                    ],
                }
            ],
            'relationships': [],
        }

    def run_metric(self, metric_id, target, parameters):
        assert target == {'table': 'actor', 'column': 'first_name'}
        assert parameters == {}
        assert metric_id in {'completeness', 'uniqueness'}
        row_ids = [1] if metric_id == 'completeness' else [2]
        return {
            'metric_id': metric_id,
            'target': target,
            'dimension': 'completeness' if metric_id == 'completeness' else 'uniqueness',
            'status': 'completed',
            'eligible': 2,
            'passing': 1,
            'violations': 1,
            'violation_ids': row_ids,
        }


def proposal(metric_id='completeness'):
    target = {'table': 'actor', 'column': 'first_name'}
    return {
        'kind': 'rule',
        'target': target,
        'title': 'Review names',
        'description': 'Propose a check for actor names.',
        'evidence': ['Schema and aggregate profile inspected.'],
        'assumptions': ['Data owner must confirm the policy.'],
        'status': 'draft',
        'rule': {'metric_id': metric_id, 'target': target, 'parameters': {}},
    }


def trial(proposals):
    return {
        'run_id': 'b_01',
        'approach': 'B',
        'provider': 'codex-task-agent',
        'model': 'gpt-5.6-sol',
        'split': 'development',
        'status': 'completed',
        'proposals': proposals,
    }


REFERENCE = {
    'reference_reviewed': False,
    'detections': [{'rule_id': 'name_present', 'row_id': 1, 'target': 'actor.first_name'}],
}
BASELINE = {
    'rules': [
        {
            'rule_id': 'name_present',
            'metric_id': 'completeness',
            'target': {'table': 'actor', 'column': 'first_name'},
            'parameters': {},
        }
    ]
}


def test_exact_rule_matches_reference_but_remains_development_only():
    result = score_trial(TinySource(), trial([proposal()]), REFERENCE, BASELINE)
    assert result['metrics']['tp'] == 1
    assert result['metrics']['fp'] == result['metrics']['fn'] == 0
    assert result['formal_final_eligible'] is False
    assert result['rule_count_executed'] == 1


def test_unmatched_rule_detections_are_false_positives_and_invalid_rule_is_skipped():
    invalid = proposal()
    invalid['rule']['metric_id'] = 'arbitrary_sql'
    result = score_trial(
        TinySource(), trial([proposal('uniqueness'), invalid]), REFERENCE, BASELINE
    )
    assert result['metrics']['tp'] == 0
    assert result['metrics']['fp'] == 1
    assert result['metrics']['fn'] == 1
    assert result['proposal_assessments'][1]['status'] == 'invalid'
    assert result['rule_count_executed'] == 1


def test_non_codex_or_incomplete_artifacts_cannot_be_scored():
    wrong = trial([proposal()])
    wrong['model'] = 'qwen3-4b-instruct-2507'
    with pytest.raises(ValueError):
        score_trial(TinySource(), wrong, REFERENCE, BASELINE)
