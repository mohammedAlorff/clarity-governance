"""Formal scores must be bound to source rows and executed original proposals."""

import copy
import json
from pathlib import Path

import pytest

from governance.evaluation import (
    complete_trial,
    freeze_manifest,
    json_hash,
    measure_trial,
    run_trial,
    source_identity,
    validate_freeze,
)
from governance.source import DemoSource
from tests.test_evaluation import MANIFEST


def test_snapshot_hash_changes_when_only_a_row_value_changes():
    source = DemoSource()
    before = source_identity(source)
    source.rows['customers'][0]['email'] = 'changed@example.test'
    after = source_identity(source)
    assert before['schema_hash'] == after['schema_hash']
    assert before['source_hash'] != after['source_hash']
    assert 'changed@example.test' not in str(after)


def test_changed_row_blocks_model_request(tmp_path):
    class NoRequests:
        provider = 'openai'
        model = 'configured-model'

        def respond(self, *args, **kwargs):
            raise AssertionError('Model must not be contacted.')

    source = DemoSource()
    source.rows['customers'][0]['name'] = 'different'
    frozen = freeze_manifest(MANIFEST, tmp_path / 'frozen.json')
    with pytest.raises(ValueError, match='row content'):
        run_trial(source, NoRequests(), 'C', frozen)


def test_runtime_contract_change_blocks_frozen_protocol(tmp_path):
    frozen = freeze_manifest(MANIFEST, tmp_path / 'frozen.json')
    frozen['runtime_contract']['sampling']['candidate_pool'] += 1
    readiness = validate_freeze(frozen)
    assert readiness['status'] == 'pending'
    assert any('runtime' in reason.lower() for reason in readiness['reasons'])


def test_freeze_requires_static_baseline_cache_attestation_and_measurable_targets():
    for change in (
        {'baseline_hash': None},
        {'schema_hash': None},
        {'cache_disabled_attested': False},
        {'targets': {'unimplemented_metric': 0.8}},
    ):
        candidate = {**copy.deepcopy(MANIFEST), **change}
        assert validate_freeze(candidate)['status'] == 'pending'


def test_original_detection_is_derived_from_executed_rule(tmp_path):
    reference = {
        'rules': [
            {'rule_id': 'required', 'metric_id': 'completeness', 'target': 'customers.email'}
        ],
        'columns': [{'target': 'customers.email'}],
        'detections': [{'rule_id': 'required', 'row_id': 4, 'target': 'customers.email'}],
    }
    manifest = {**copy.deepcopy(MANIFEST), 'reference_hash': json_hash(reference)}
    frozen = freeze_manifest(manifest, tmp_path / 'frozen.json')
    proposal = {
        'kind': 'rule',
        'target': {'table': 'customers', 'column': 'email'},
        'rule': {
            'metric_id': 'completeness',
            'target': {'table': 'customers', 'column': 'email'},
            'parameters': {},
        },
    }
    artifact = {
        'run_id': 'measured-run',
        'case_id': 'default',
        'status': 'awaiting_human_review',
        'source_hash': frozen['source_hash'],
        'reference_hash': frozen['reference_hash'],
        'manifest_hash': frozen['manifest_hash'],
        'runtime_contract': frozen['runtime_contract'],
        'original_proposals': [proposal],
    }
    measured = measure_trial(DemoSource(), artifact, frozen)
    assert measured['original_measurement']['results'][0]['violation_ids'] == [4]
    review = {
        'reviewer': 'reviewer',
        'reference_hash': frozen['reference_hash'],
        'artifact_run_id': artifact['run_id'],
        'original_proposals_hash': json_hash([proposal]),
        'review_seconds': 15,
        'original_detections': None,
        'detections': [],
        'proposal_assessments': [
            {
                'proposal_index': 0,
                'correct': True,
                'applicable': True,
                'useful': True,
                'reference_rule_ids': ['required'],
            }
        ],
    }
    completed = complete_trial(measured, review, reference)
    assert completed['original_metrics']['tp'] == 1
    assert completed['reviewed_metrics']['fn'] == 1
    assert completed['measured_original_detections'] == reference['detections']
    review['original_detections'] = [
        {'rule_id': 'required', 'row_id': 5, 'target': 'customers.email'}
    ]
    with pytest.raises(ValueError, match='measured'):
        complete_trial(measured, review, reference)


def test_zero_proposals_cannot_claim_reference_detection():
    reference = {
        'rules': [{'rule_id': 'required', 'metric_id': 'completeness', 'target': 't.a'}],
        'columns': [{'target': 't.a'}],
        'detections': [{'rule_id': 'required', 'row_id': 1, 'target': 't.a'}],
    }
    artifact = {
        'run_id': 'empty',
        'status': 'awaiting_human_review',
        'reference_hash': json_hash(reference),
        'original_proposals': [],
    }
    review = {
        'reviewer': 'reviewer',
        'reference_hash': artifact['reference_hash'],
        'artifact_run_id': 'empty',
        'original_proposals_hash': json_hash([]),
        'proposal_assessments': [],
        'original_detections': reference['detections'],
        'detections': [],
    }
    with pytest.raises(ValueError, match='executed'):
        complete_trial(artifact, review, reference)


def test_public_fault_reference_candidate_is_complete_but_unapproved():
    from governance.evaluation_review import reference_catalog

    root = Path(__file__).resolve().parents[1]
    candidate = json.loads(
        (root / 'evaluation/sakila/fault-reference.review-candidate.json').read_text()
    )
    original = json.loads(
        (root / 'evaluation/sakila/fault-reference.machine-draft.json').read_text()
    )
    rules, columns = reference_catalog(candidate)
    assert candidate['reference_reviewed'] is False
    assert len(rules) == 7
    assert len(columns) == 12
    assert candidate['detections'] == original['detections']
