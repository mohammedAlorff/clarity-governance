import hashlib
import json

import pytest

from governance.evaluation import json_hash
from scripts import study_archive


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def test_archive_keeps_distinct_artifacts_and_rejects_tampering(tmp_path, monkeypatch):
    pilot = tmp_path / 'pilot'
    archive = tmp_path / 'archive'
    run_id = 'b_contract_01'
    monkeypatch.setattr(study_archive, 'PILOT', pilot)
    monkeypatch.setattr(study_archive, 'ARCHIVE', archive)
    monkeypatch.setattr(study_archive, 'RUNS', ((run_id, 'B'),))

    columns = [
        {'name': f'column_{index}', 'data_type': 'int', 'nullable': False, 'key': ''}
        for index in range(12)
    ]
    schema = {'tables': [{'name': 'example', 'columns': columns}], 'relationships': []}
    targets = [{'table': 'example', 'column': column['name']} for column in columns]
    profiles = [
        {
            'status': 'completed',
            'action': 'profile',
            'result': {
                'target': target,
                'row_count': 10,
                'null_count': 0,
                'non_null_count': 10,
                'distinct_count': 10,
            },
        }
        for target in targets
    ]
    evidence = {
        'run_id': run_id,
        'approach': 'B',
        'split': 'development',
        'source_call_count': 13,
        'source_outputs': [
            {'status': 'completed', 'action': 'schema', 'result': schema},
            *profiles,
        ],
    }
    actions = [
        {
            'action': 'schema',
            'status': 'completed',
            'result': {'tables': 1, 'columns': 12, 'relationships': 0},
        },
        *[
            {
                'action': 'profile',
                'status': 'completed',
                'target': target,
                'result': {
                    'row_count': 10,
                    'null_count': 0,
                    'non_null_count': 10,
                    'distinct_count': 10,
                },
            }
            for target in targets
        ],
    ]
    trial = {
        'run_id': run_id,
        'approach': 'B',
        'model': 'gpt-5.6-sol',
        'provider': 'codex-task-agent',
        'split': 'development',
        'status': 'completed',
        'proposals': [],
    }
    score = {
        'run_id': run_id,
        'approach': 'B',
        'model': trial['model'],
        'provider': trial['provider'],
        'status': 'awaiting_human_review',
        'formal_final_eligible': False,
        'reference_reviewed': False,
        'trial_hash': json_hash(trial),
        'schema_projection_hash': json_hash(schema),
        'source_hash': 'a' * 64,
        'reference_hash': 'b' * 64,
        'proposal_count': 0,
        'proposal_assessments': [],
        'rule_count_executed': 0,
        'metrics': {'tp': 0, 'fp': 0, 'fn': 8, 'precision': None, 'recall': 0.0, 'f1': None},
    }
    _write(pilot / 'evidence' / f'{run_id}.json', evidence)
    _write(pilot / 'trials' / f'{run_id}.json', trial)
    _write(pilot / 'scores' / f'{run_id}.json', score)
    (pilot / f'{run_id}.jsonl').write_text(
        ''.join(json.dumps(action) + '\n' for action in actions), encoding='utf-8'
    )

    output = study_archive.archive()
    summary = json.loads(output.read_text(encoding='utf-8'))
    assert len(summary['artifacts']) == 4
    assert {entry['path'].split('/')[-1] for entry in summary['artifacts']} == {
        'evidence.json',
        'actions.jsonl',
        'original_proposals.json',
        'technical_score.json',
    }
    assert all(
        hashlib.sha256((archive / entry['path']).read_bytes()).hexdigest() == entry['sha256']
        for entry in summary['artifacts']
    )

    trial['unscored_change'] = True
    _write(pilot / 'trials' / f'{run_id}.json', trial)
    with pytest.raises(ValueError, match='Inconsistent'):
        study_archive.archive()
    trial.pop('unscored_change')
    _write(pilot / 'trials' / f'{run_id}.json', trial)
    actions[1]['target'] = {'table': 'example', 'column': 'column_11'}
    (pilot / f'{run_id}.jsonl').write_text(
        ''.join(json.dumps(action) + '\n' for action in actions), encoding='utf-8'
    )
    with pytest.raises(ValueError, match='Fixed evidence/order'):
        study_archive.archive()
