"""Archive the six blinded Codex proxy runs with an inspectable summary.

Only sanitized evidence, bounded action logs, original proposals, and technical
scores are copied. This development pilot is not a formal application-provider
or human-reviewed held-out evaluation.
"""

import hashlib
import json
import shutil
import statistics
from datetime import datetime, timezone
from pathlib import Path

from governance.evaluation import json_hash

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / 'data' / 'study-pilot'
ARCHIVE = ROOT / 'evaluation' / 'codex-pilot'
RUNS = tuple(
    (f'{approach.lower()}_contract_{number:02d}', approach)
    for number in range(1, 4)
    for approach in ('B', 'C')
)


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stats(values):
    available = [value for value in values if value is not None]
    return {
        'observed': len(available),
        'mean': statistics.mean(available) if available else None,
        'sample_sd': statistics.stdev(available) if len(available) > 1 else None,
    }


def archive():
    inspected = []
    hashes = set()
    references = set()
    schemas = set()
    files = []
    for run_id, approach in RUNS:
        paths = {
            'evidence': PILOT / 'evidence' / f'{run_id}.json',
            'actions': PILOT / f'{run_id}.jsonl',
            'original_proposals': PILOT / 'trials' / f'{run_id}.json',
            'technical_score': PILOT / 'scores' / f'{run_id}.json',
        }
        if any(not path.is_file() or path.is_symlink() for path in paths.values()):
            raise FileNotFoundError(f'Missing or unsafe run artifact: {run_id}')
        evidence, trial, score = (
            _read(paths[key]) for key in ('evidence', 'original_proposals', 'technical_score')
        )
        actions = [
            json.loads(line) for line in paths['actions'].read_text(encoding='utf-8').splitlines()
        ]
        if (
            evidence.get('run_id') != run_id
            or evidence.get('approach') != approach
            or evidence.get('split') != 'development'
            or trial.get('run_id') != run_id
            or trial.get('approach') != approach
            or trial.get('model') != 'gpt-5.6-sol'
            or trial.get('provider') != 'codex-task-agent'
            or trial.get('split') != 'development'
            or trial.get('status') != 'completed'
            or score.get('run_id') != run_id
            or score.get('approach') != approach
            or score.get('model') != trial.get('model')
            or score.get('provider') != trial.get('provider')
            or score.get('status') != 'awaiting_human_review'
            or score.get('formal_final_eligible') is not False
            or score.get('reference_reviewed') is not False
            or score.get('trial_hash') != json_hash(trial)
            or score.get('schema_projection_hash')
            != json_hash(evidence['source_outputs'][0]['result'])
            or score.get('proposal_count') != len(trial.get('proposals', []))
            or not 1 <= len(actions) <= 20
            or actions[0].get('action') != 'schema'
            or evidence.get('source_call_count') != len(evidence.get('source_outputs', []))
            or evidence['source_call_count'] != (13 if approach == 'B' else 1)
        ):
            raise ValueError(f'Inconsistent development-pilot artifact: {run_id}')
        if approach == 'B' and (
            len(actions) != 13 or any(action['action'] != 'profile' for action in actions[1:])
        ):
            raise ValueError(f'Fixed run deviated from the 13-call sequence: {run_id}')
        schema = evidence['source_outputs'][0]['result']
        schema_summary = {
            'tables': len(schema['tables']),
            'columns': sum(len(table['columns']) for table in schema['tables']),
            'relationships': len(schema['relationships']),
        }
        if actions[0].get('result') != schema_summary:
            raise ValueError(f'Schema action disagrees with supplied evidence: {run_id}')
        if approach == 'B':
            targets = [
                {'table': table['name'], 'column': column['name']}
                for table in schema['tables']
                for column in table['columns']
            ]
            for target, action, output in zip(
                targets, actions[1:], evidence['source_outputs'][1:], strict=True
            ):
                result = output['result']
                profile_summary = {
                    key: result[key]
                    for key in ('row_count', 'null_count', 'non_null_count', 'distinct_count')
                }
                if (
                    output.get('action') != 'profile'
                    or output.get('status') != 'completed'
                    or result.get('target') != target
                    or action.get('target') != target
                    or action.get('result') != profile_summary
                ):
                    raise ValueError(f'Fixed evidence/order disagrees with action log: {run_id}')
        if approach == 'B' and any(action.get('status') != 'completed' for action in actions):
            raise ValueError(f'Incomplete fixed source action in run: {run_id}')
        hashes.add(score['source_hash'])
        references.add(score['reference_hash'])
        schemas.add(score['schema_projection_hash'])
        assessments = score['proposal_assessments']
        inspected.append(
            {
                'run_id': run_id,
                'approach': approach,
                'source_actions': len(actions),
                'failed_source_actions': sum(
                    action.get('status') != 'completed' for action in actions
                ),
                'positive_metric_probes': sum(
                    action.get('action') == 'metric'
                    and action.get('status') == 'completed'
                    and action.get('result', {}).get('violations', 0) > 0
                    for action in actions
                ),
                'proposal_count': score['proposal_count'],
                'description_count': sum(p['kind'] == 'description' for p in trial['proposals']),
                'clarification_count': sum(
                    p['status'] == 'needs_clarification' for p in trial['proposals']
                ),
                'invalid_proposals': sum(a['status'] == 'invalid' for a in assessments),
                'executed_rules': score['rule_count_executed'],
                'exact_reference_rules': len(
                    {
                        a['matched_reference_rule_id']
                        for a in assessments
                        if a.get('matched_reference_rule_id')
                    }
                ),
                'scoring_status': score['status'],
                'metrics': score['metrics'],
            }
        )
        for kind, source in paths.items():
            destination = ARCHIVE / 'artifacts' / run_id / f'{kind}{source.suffix}'
            files.append((kind, source, destination))
    if len(hashes) != 1 or len(references) != 1 or len(schemas) != 1:
        raise ValueError('Source, schema, or reference changed across pilot runs.')
    by_approach = {}
    for approach in ('B', 'C'):
        runs = [run for run in inspected if run['approach'] == approach]
        by_approach[approach] = {
            'runs': len(runs),
            'source_actions': _stats([run['source_actions'] for run in runs]),
            'failed_source_actions': sum(run['failed_source_actions'] for run in runs),
            'positive_metric_probes': sum(run['positive_metric_probes'] for run in runs),
            'proposal_count': _stats([run['proposal_count'] for run in runs]),
            'invalid_proposals': sum(run['invalid_proposals'] for run in runs),
            'exact_reference_rules': sum(run['exact_reference_rules'] for run in runs),
            'tp': _stats([run['metrics']['tp'] for run in runs]),
            'fp': _stats([run['metrics']['fp'] for run in runs]),
            'fn': _stats([run['metrics']['fn'] for run in runs]),
            'precision': _stats([run['metrics']['precision'] for run in runs]),
            'recall': _stats([run['metrics']['recall'] for run in runs]),
            'f1': _stats([run['metrics']['f1'] for run in runs]),
        }
    manifest = {
        'study_type': 'exploratory development Codex proxy',
        'formal_final_eligible': False,
        'reference_reviewed': False,
        'model': 'gpt-5.6-sol',
        'source_hash': next(iter(hashes)),
        'schema_projection_hash': next(iter(schemas)),
        'reference_hash': next(iter(references)),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'run_order': [run_id for run_id, _ in RUNS],
        'calibration_excluded': [
            f'{approach.lower()}_proxy_{number:02d}'
            for number in range(1, 4)
            for approach in ('B', 'C')
        ],
        'runs': inspected,
        'by_approach': by_approach,
        'unmeasured': [
            'independent held-out performance',
            'human proposal quality',
            'human review time',
            'uncached status',
            'token usage',
            'cost',
            'comparable model-only latency',
            'adaptive decision-round compliance',
        ],
        'artifacts': [],
    }
    for kind, source, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        manifest['artifacts'].append(
            {
                'run_id': destination.parent.name,
                'kind': kind,
                'path': str(destination.relative_to(ARCHIVE)).replace('\\', '/'),
                'sha256': _sha256(destination),
            }
        )
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    output = ARCHIVE / 'summary.json'
    output.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    print(archive())
