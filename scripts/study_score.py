"""Score Codex development-pilot proposals on the isolated fault fixture.

This is an exploratory proxy for B/C, not the application's provider trial or a
human-reviewed held-out result. Proposed rules are evaluated read-only in this
scoring process and are never approved or activated in the application.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from dotenv import dotenv_values

from governance.agent import _validate_proposals
from governance.evaluation import detection_metrics, json_hash, run_baseline
from governance.privacy import model_view
from governance.source import MySQLSource
from scripts.public_data_faults import ENV, SCHEMA, STATE, USER, snapshot
from scripts.public_mysql import DATADIR, PORT, connect

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'evaluation' / 'sakila' / 'fault-reference.machine-draft.json'
BASELINE = ROOT / 'evaluation' / 'sakila' / 'fault-baseline.json'


def _canonical(rule):
    return json.dumps(rule, sort_keys=True, separators=(',', ':'), allow_nan=False)


def score_trial(source, trial, reference, baseline):
    """Validate, execute, and score original rules with strict exact mapping."""
    if (
        not isinstance(trial, dict)
        or trial.get('approach') not in {'B', 'C'}
        or trial.get('model') != 'gpt-5.6-sol'
        or trial.get('provider') != 'codex-task-agent'
        or trial.get('split') != 'development'
        or trial.get('status') != 'completed'
        or not isinstance(trial.get('run_id'), str)
        or not trial['run_id']
        or not isinstance(trial.get('proposals'), list)
        or len(trial['proposals']) > 100
    ):
        raise ValueError('Only completed Codex GPT-5.6 development B/C artifacts are accepted.')
    if reference.get('reference_reviewed') is not False:
        raise ValueError('This development scorer expects a machine-authored reference.')
    schema = source.get_schema()
    lookup = {
        _canonical({key: value for key, value in item.items() if key != 'rule_id'}): item['rule_id']
        for item in baseline['rules']
    }
    rules, mapped, assessments = [], {}, []
    for index, proposal in enumerate(trial['proposals']):
        try:
            validated = _validate_proposals([proposal], schema)[0]
        except (ValueError, TypeError, KeyError):
            assessments.append({'proposal_index': index, 'status': 'invalid'})
            continue
        if validated['kind'] != 'rule':
            assessments.append({'proposal_index': index, 'status': 'description_unassessed'})
            continue
        if validated['status'] == 'needs_clarification':
            assessments.append({'proposal_index': index, 'status': 'clarification_unexecuted'})
            continue
        if len(rules) >= 25:
            assessments.append({'proposal_index': index, 'status': 'rule_cap_unexecuted'})
            continue
        rule = validated['rule']
        candidate = f'candidate_{index}'
        matched = lookup.get(_canonical(rule))
        mapped[candidate] = matched or f'unmapped_{index}'
        rules.append({'rule_id': candidate, **rule})
        assessments.append(
            {
                'proposal_index': index,
                'status': 'executed_read_only',
                'matched_reference_rule_id': matched,
            }
        )

    result = run_baseline(source, {'rules': rules})
    detections = [{**item, 'rule_id': mapped[item['rule_id']]} for item in result['detections']]
    metrics = detection_metrics(detections, reference['detections'])
    return {
        'run_id': trial['run_id'],
        'approach': trial['approach'],
        'provider': trial['provider'],
        'model': trial['model'],
        'split': 'development',
        'reference_reviewed': False,
        'formal_final_eligible': False,
        'scoring': 'strict exact rule configuration; unmatched detections count as false positives',
        'status': result['status'],
        'proposal_count': len(trial['proposals']),
        'rule_count_executed': len(rules),
        'proposal_assessments': assessments,
        'detections': detections,
        'metrics': metrics,
        'rule_results': result['results'],
        'source_rule_execution': 'read-only technical scoring; no application approval or activation',
    }


def _open_fault_source():
    state = json.loads(STATE.read_text(encoding='utf-8'))
    if state.get('fixture_version') != 1 or state.get('schema') != SCHEMA:
        raise RuntimeError('Unknown fault fixture; refusing to connect.')
    admin = connect()  # Verifies only the isolated 127.0.0.1:3307 data directory.
    try:
        if snapshot(admin, 'sakila') != state['copied_source_rows_sha256']:
            raise RuntimeError('Public source snapshot changed.')
        if snapshot(admin, SCHEMA) != state['fixture_rows_sha256']:
            raise RuntimeError('Fault fixture snapshot changed.')
    finally:
        admin.close()
    values = dotenv_values(ENV)
    if (
        values.get('MYSQL_HOST') != '127.0.0.1'
        or values.get('MYSQL_PORT') != str(PORT)
        or values.get('MYSQL_DATABASE') != SCHEMA
        or values.get('MYSQL_USER') != USER
        or not values.get('MYSQL_PASSWORD')
    ):
        raise RuntimeError('Unexpected fault reader configuration.')
    reader = pymysql.connect(
        host='127.0.0.1',
        port=PORT,
        user=USER,
        password=values['MYSQL_PASSWORD'],
        database=SCHEMA,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
        read_timeout=6,
        charset='utf8mb4',
    )
    with reader.cursor() as cursor:
        cursor.execute('SELECT @@datadir AS directory')
        if Path(cursor.fetchone()['directory']).resolve() != DATADIR.resolve():
            reader.close()
            raise RuntimeError('Reader target is outside the isolated test server.')
    return MySQLSource(reader, SCHEMA), state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    trial = json.loads(args.trial.read_text(encoding='utf-8'))
    reference = json.loads(REFERENCE.read_text(encoding='utf-8'))
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    source, state = _open_fault_source()
    try:
        result = score_trial(source, trial, reference, baseline)
        schema_projection_hash = json_hash(model_view(source.get_schema()))
    finally:
        source.close()
    result.update(
        {
            'scored_at': datetime.now(timezone.utc).isoformat(),
            'source_hash': state['fixture_rows_sha256'],
            'reference_hash': json_hash(reference),
            'trial_hash': json_hash(trial),
            'schema_projection_hash': schema_projection_hash,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(
        json.dumps(
            {
                'run_id': result['run_id'],
                'approach': result['approach'],
                'status': result['status'],
                'metrics': result['metrics'],
                'output': str(args.output),
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
