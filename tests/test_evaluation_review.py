import copy
import json

import pytest

from governance.evaluation import complete_trial, json_hash, main, summarize_trials


def fixture():
    reference = {
        'rules': [
            {'rule_id': 'required', 'metric_id': 'completeness', 'target': 't.a'},
            {'rule_id': 'unique', 'metric_id': 'uniqueness', 'target': 't.a'},
        ],
        'columns': [{'target': 't.a'}, {'target': 't.b'}],
        'detections': [{'rule_id': 'required', 'row_id': 1, 'target': 't.a'}],
    }
    artifact = {
        'run_id': 'test-run',
        'status': 'awaiting_human_review',
        'reference_hash': json_hash(reference),
        'source_hash': 'source1',
        'original_proposals': [
            {
                'kind': 'rule',
                'target': {'table': 't', 'column': 'a'},
                'rule': {'metric_id': 'completeness', 'target': {'table': 't', 'column': 'a'}},
            },
            {'kind': 'description', 'target': {'table': 't', 'column': 'a'}},
            {'kind': 'description', 'target': {'table': 't', 'column': 'b'}},
        ],
    }
    artifact['original_measurement'] = {
        'run_id': artifact['run_id'],
        'source_hash': artifact['source_hash'],
        'proposals_hash': json_hash(artifact['original_proposals']),
        'results': [
            {'proposal_index': 0, 'status': 'completed', 'violations': 1, 'violation_ids': [1]}
        ],
    }
    artifact['original_measurement_hash'] = json_hash(artifact['original_measurement'])
    review = {
        'artifact_run_id': artifact['run_id'],
        'original_proposals_hash': json_hash(artifact['original_proposals']),
        'reviewer': 'test reviewer',
        'reference_hash': artifact['reference_hash'],
        'review_seconds': 25,
        'original_detections': reference['detections'],
        'detections': reference['detections'],
        'proposal_assessments': [
            {
                'proposal_index': 0,
                'correct': True,
                'applicable': True,
                'useful': False,
                'reference_rule_ids': ['required'],
            },
            {
                'proposal_index': 1,
                'supported': True,
                'unsupported_claims': False,
                'abstained': False,
            },
            {
                'proposal_index': 2,
                'supported': False,
                'unsupported_claims': False,
                'abstained': True,
            },
        ],
    }
    return artifact, review, reference


def test_review_scores_original_proposals_and_deduplicated_coverage():
    artifact, review, reference = fixture()
    original = copy.deepcopy(artifact)
    result = complete_trial(artifact, review, reference)
    quality = result['proposal_quality']
    assert quality['status'] == 'complete'
    assert quality['rules']['correct'] == 1
    assert quality['rules']['useful'] == 0
    assert quality['rules']['reference_coverage'] == 0.5
    assert quality['documentation']['supported_columns'] == 1
    assert quality['documentation']['supported_coverage'] == 0.5
    assert quality['documentation']['abstentions'] == 1
    assert result['detection_breakdown']['original']['completeness']['tp'] == 1
    assert result['detection_breakdown']['original']['uniqueness']['precision'] is None
    assert artifact == original
    assert result['original_proposals'] == artifact['original_proposals']


@pytest.mark.parametrize(
    'change',
    [
        'missing',
        'duplicate',
        'unknown',
        'string_bool',
        'contradiction',
        'wrong_target',
        'incorrect_with_mapping',
        'wrong_metric',
        'multiple_mappings',
    ],
)
def test_review_rejects_incomplete_or_inconsistent_assessment(change):
    artifact, review, reference = fixture()
    rows = review['proposal_assessments']
    if change == 'missing':
        rows.pop()
    if change == 'duplicate':
        rows[2] = rows[1]
    if change == 'unknown':
        rows[0]['reference_rule_ids'] = ['invented']
    if change == 'string_bool':
        rows[0]['correct'] = 'yes'
    if change == 'contradiction':
        rows[1]['abstained'] = True
    if change == 'wrong_target':
        reference['rules'][0]['target'] = 't.b'
        artifact['reference_hash'] = review['reference_hash'] = json_hash(reference)
    if change == 'incorrect_with_mapping':
        rows[0]['correct'] = False
    if change == 'wrong_metric':
        artifact['original_proposals'][0]['rule']['metric_id'] = 'uniqueness'
        review['original_proposals_hash'] = json_hash(artifact['original_proposals'])
        artifact['original_measurement']['proposals_hash'] = review['original_proposals_hash']
        artifact['original_measurement_hash'] = json_hash(artifact['original_measurement'])
    if change == 'multiple_mappings':
        rows[0]['reference_rule_ids'] = ['required', 'unique']
    with pytest.raises(ValueError):
        complete_trial(artifact, review, reference)


def test_legacy_review_remains_explicitly_unassessed():
    artifact, review, reference = fixture()
    del review['proposal_assessments']
    review['original_detections'] = None
    result = complete_trial(artifact, review, reference)
    assert result['proposal_quality']['status'] == 'pending'
    assert result['status'] == 'reviewed_unmeasured'


@pytest.mark.parametrize('seconds', [-1, True, float('nan'), '25'])
def test_invalid_review_duration_rejected(seconds):
    artifact, review, reference = fixture()
    review['review_seconds'] = seconds
    with pytest.raises(ValueError):
        complete_trial(artifact, review, reference)


def test_review_template_has_no_automated_human_judgments(tmp_path, capsys):
    artifact, _, reference = fixture()
    for name, value in [('artifact', artifact), ('reference', reference)]:
        (tmp_path / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')
    output = tmp_path / 'review.json'
    args = [
        'review-template',
        str(tmp_path / 'artifact.json'),
        str(tmp_path / 'reference.json'),
        str(output),
    ]
    assert main(args) == 0
    template = json.loads(output.read_text(encoding='utf-8'))
    assert template['reviewer'] is None
    assert template['original_detections'] is None
    assert template['detections'] is None
    assert template['proposal_assessments'][0]['correct'] is None
    assert len(template['proposal_assessments']) == 3
    assert main(args) == 2  # Cannot overwrite a human's review.
    with pytest.raises(ValueError):
        complete_trial(artifact, template, reference)


def test_efficiency_summary_excludes_ineligible_runs_and_preserves_unknowns():
    from tests.test_evaluation import trial

    a, b, excluded = trial('C', 'a'), trial('C', 'b'), trial('C', 'excluded')
    for run in (a, b, excluded):
        run['elapsed_seconds'] = 10
        run['usage'] = {'tool_calls': 8, 'total_tokens': 100, 'usage_known': True, 'cost_usd': None}
    a['usage']['cost_usd'] = 0.02
    a['human_review'] = {'review_seconds': 30}
    b['usage']['usage_known'] = False
    excluded['split'] = 'development'
    excluded['elapsed_seconds'] = 999
    result = summarize_trials([a, b, excluded])
    group = result['efficiency']['C']
    assert group['elapsed_seconds'] == {'n': 2, 'mean': 10, 'stdev': 0.0}
    assert group['total_tokens']['n'] == 1
    assert group['cost_usd']['mean'] == 0.02
    assert group['cost_usd']['n'] == 1
    assert group['review_seconds']['mean'] == 30
    assert result['cases']['default']['efficiency'] == result['efficiency']


def test_summary_reports_assessed_and_unassessed_trials_separately():
    from tests.test_evaluation import trial

    artifact, review, reference = fixture()
    assessed = {**trial('C', 'one'), **complete_trial(artifact, review, reference)}
    unassessed = trial('C', 'two')
    result = summarize_trials([assessed, unassessed, assessed])
    quality = result['proposal_quality']['C']
    assert quality['assessed_trials'] == 1
    assert quality['unassessed_trials'] == 1
    assert quality['rules']['correct_rate']['mean'] == 1
    assert quality['documentation']['supported_coverage']['mean'] == 0.5
    assert result['by_error_type']['original']['completeness']['C']['recall']['mean'] == 1


def test_full_measurement_readiness_requires_human_assessments_and_effort():
    from governance.evaluation import measurement_readiness
    from tests.test_evaluation import MANIFEST, trial

    artifact, review, reference = fixture()
    runs = [trial(a, a + str(i)) for a in ('B', 'C') for i in range(3)]
    assert measurement_readiness(MANIFEST, runs)['status'] == 'pending'
    completed = complete_trial(artifact, review, reference)
    runs = [{**run, **copy.deepcopy(completed), 'run_id': run['run_id']} for run in runs]
    assert measurement_readiness(MANIFEST, runs)['status'] == 'ready'
    del runs[0]['human_review']['review_seconds']
    assert measurement_readiness(MANIFEST, runs)['status'] == 'pending'


def test_assessments_cannot_be_reused_for_another_run_or_changed_original():
    artifact, review, reference = fixture()
    artifact['run_id'] = 'different-run'
    with pytest.raises(ValueError):
        complete_trial(artifact, review, reference)
    artifact['run_id'] = 'test-run'
    artifact['original_proposals'][0]['title'] = 'Changed proposal'
    with pytest.raises(ValueError):
        complete_trial(artifact, review, reference)


def test_error_breakdown_uses_same_identifier_normalization_as_overall():
    from governance.evaluation import detection_metrics
    from governance.evaluation_review import detection_breakdown

    reference = {
        'rules': [{'rule_id': '123', 'metric_id': 'completeness', 'target': 't.a'}],
        'columns': [{'target': 't.a'}],
        'detections': [{'rule_id': '123', 'row_id': 1, 'target': 't.a'}],
    }
    predicted = [{'rule_id': 123, 'row_id': 1, 'target': 't.a'}]
    overall = detection_metrics(predicted, reference['detections'])
    assert detection_breakdown(predicted, reference) == {'completeness': overall}


def test_final_cli_includes_counts_and_stays_pending_without_full_assessments(tmp_path, capsys):
    from governance.evaluation import (
        complete_baseline,
        freeze_manifest,
        run_baseline,
        source_identity,
    )
    from governance.source import DemoSource
    from tests.test_evaluation import BASELINE, MANIFEST, trial

    artifact, review, reference = fixture()
    manifest = {**copy.deepcopy(MANIFEST), 'reference_hash': json_hash(reference)}
    path = tmp_path / 'frozen.json'
    frozen = freeze_manifest(manifest, path)
    runs = []
    for approach in ('B', 'C'):
        for index in range(3):
            pending = {
                **trial(approach, approach + str(index)),
                **copy.deepcopy(artifact),
                'run_id': approach + str(index),
                'budgets': frozen['budgets'],
                'manifest_hash': frozen['manifest_hash'],
                'started_at': '2099-01-01T00:00:00Z',
            }
            pending['source_hash'] = frozen['source_hash']
            pending['source_hash_after'] = frozen['source_hash']
            pending['source_identity'] = {
                'source_hash': frozen['source_hash'],
                'schema_hash': frozen['schema_hash'],
            }
            pending['runtime_contract'] = frozen['runtime_contract']
            pending['original_measurement']['run_id'] = pending['run_id']
            pending['original_measurement']['source_hash'] = frozen['source_hash']
            pending['original_measurement_hash'] = json_hash(pending['original_measurement'])
            assessment = {**review, 'artifact_run_id': pending['run_id']}
            runs.append(complete_trial(pending, assessment, reference))
    trials_path = tmp_path / 'trials.json'
    trials_path.write_text(json.dumps(runs), encoding='utf-8')
    references_path = tmp_path / 'references.json'
    references_path.write_text(json.dumps({'default': reference}), encoding='utf-8')
    source = DemoSource()
    static = run_baseline(source, BASELINE)
    static.update(
        run_id='static-run',
        case_id='default',
        split='held_out',
        source_hash=frozen['source_hash'],
        source_hash_after=frozen['source_hash'],
        source_identity=source_identity(source),
        baseline_hash=frozen['baseline_hash'],
        reference_hash=frozen['reference_hash'],
        manifest_hash=frozen['manifest_hash'],
        runtime_contract=frozen['runtime_contract'],
        budgets=frozen['budgets'],
        started_at='2099-01-01T00:00:00Z',
        provider='static',
        model=None,
        cached=False,
    )
    static_review = {
        'reviewer': 'test reviewer',
        'review_seconds': 12,
        'reference_hash': frozen['reference_hash'],
        'artifact_run_id': static['run_id'],
        'baseline_hash': frozen['baseline_hash'],
        'rule_mappings': {'required': None},
    }
    with pytest.raises(ValueError, match='metrics and targets'):
        complete_baseline(
            static,
            {**static_review, 'rule_mappings': {'required': 'unique'}},
            reference,
            frozen,
        )
    scored_static = complete_baseline(static, static_review, reference, frozen)
    for field, value in (
        ('provider', 'openai'),
        ('cached', True),
        ('started_at', '2000-01-01T00:00:00Z'),
        ('budgets', {'max_calls': 1}),
    ):
        modified = {**static, field: value}
        with pytest.raises(ValueError):
            complete_baseline(modified, static_review, reference, frozen)
    baselines_path = tmp_path / 'baselines.json'
    baselines_path.write_text(json.dumps([scored_static]), encoding='utf-8')
    args = ['final', str(path), str(trials_path), str(references_path), str(baselines_path)]
    assert main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['measurement_readiness']['status'] == 'ready'
    counts = output['summary']['by_error_type']['original']['completeness']['C']
    assert counts['tp'] == {'n': 3, 'mean': 1, 'stdev': 0.0}
    assert counts['reference_count']['mean'] == 1
    assert output['summary']['cases']['default']['original']['A']['fp']['mean'] == 1
    assert output['summary']['efficiency']['A']['tool_calls']['mean'] == static['tool_calls']
    trials_path.write_text(
        json.dumps(runs + [None, {'split': 'development'}, copy.deepcopy(runs[0])]),
        encoding='utf-8',
    )
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['excluded_frozen_input_trials'] == 3
    altered = copy.deepcopy(runs)
    altered[0]['original_metrics']['tp'] = 999
    trials_path.write_text(json.dumps(altered), encoding='utf-8')
    assert main(args) == 2
    altered_output = json.loads(capsys.readouterr().out)
    assert altered_output['eligible_trials']['B'] == 2
    assert altered_output['excluded_frozen_input_trials'] == 1
    altered = copy.deepcopy(runs)
    altered[0]['usage']['cached_tokens'] = 1
    trials_path.write_text(json.dumps(altered), encoding='utf-8')
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)['eligible_trials']['B'] == 2
    baselines_path.write_text(
        json.dumps([{**scored_static, 'metrics': {'tp': 999}}]), encoding='utf-8'
    )
    trials_path.write_text(json.dumps(runs), encoding='utf-8')
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)['excluded_baselines'] == 1
    baselines_path.write_text(json.dumps([scored_static]), encoding='utf-8')
    for run in runs:
        del run['proposal_quality']
    trials_path.write_text(json.dumps(runs), encoding='utf-8')
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)['measurement_readiness']['status'] == 'pending'
