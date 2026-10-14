"""Contract checks for the development pilot fixtures, not research results."""

import json
from pathlib import Path

import pytest

from governance.evaluation import detection_metrics, freeze_manifest, run_baseline, validate_freeze
from governance.source import DemoSource

KIT = Path(__file__).resolve().parents[1] / 'evaluation' / 'pilot'


def read_fixture(name):
    return json.loads((KIT / name).read_text(encoding='utf-8'))


def test_development_baseline_and_explicit_reference_stay_in_sync():
    source = DemoSource()
    try:
        baseline = read_fixture('baseline.json')
        reference = read_fixture('reference.machine-draft.json')
        output = run_baseline(source, baseline)
        assert output['status'] == 'awaiting_human_review'
        assert len(output['results']) == 8
        assert {rule['metric_id'] for rule in baseline['rules']} == {
            'completeness',
            'uniqueness',
            'range',
            'allowed_values',
            'pattern',
            'column_compare',
            'referential',
        }
        assert detection_metrics(output['detections'], reference['detections']) == {
            'tp': 9,
            'fp': 0,
            'fn': 0,
            'precision': 1,
            'recall': 1,
            'f1': 1,
            'predicted_count': 9,
            'reference_count': 9,
        }
        assert reference['reference_reviewed'] is False
        assert reference['authorship'] == 'machine-authored'
        assert reference['split'] == 'development'
    finally:
        source.close()


def test_protocol_template_cannot_be_frozen_as_approved_evidence(tmp_path):
    manifest = read_fixture('protocol.template.json')
    assert manifest['reference_reviewed'] is False
    assert manifest['targets_approved'] is False
    assert manifest['split'] == 'development'
    assert 'manifest_hash' not in manifest
    assert validate_freeze(manifest)['status'] == 'pending'
    with pytest.raises(ValueError):
        freeze_manifest(manifest, tmp_path / 'frozen.json')
    assert not (tmp_path / 'frozen.json').exists()


def test_human_review_template_contains_no_implied_review():
    review = read_fixture('human-review.template.json')
    assert review['reviewer'] is None
    assert review['reference_hash'] is None
    assert review['review_seconds'] is None
    assert review['original_detections'] is None
    assert review['detections'] == []
