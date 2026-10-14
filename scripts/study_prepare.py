"""Prepare reproducible sanitized evidence for a Codex development pilot.

This uses the same guarded, audited read-only CLI as adaptive trial agents.
The fixed approach receives schema plus every column profile in schema order;
the adaptive approach starts with schema only. Neither sees raw cell values.
"""

import argparse
import io
import json

from scripts.study_tool import LOG_DIR, RUN_ID
from scripts.study_tool import main as tool_main


def _call(run_id, *action):
    output = io.StringIO()
    if tool_main(['--run-id', run_id, *action], output=output) != 0:
        raise RuntimeError(f'Guarded study action failed: {action[0]}')
    response = json.loads(output.getvalue())
    if response.get('status') != 'completed':
        raise RuntimeError(f'Guarded study action did not complete: {action[0]}')
    return response


def prepare(run_id, approach):
    if not RUN_ID.fullmatch(run_id) or approach not in {'B', 'C'}:
        raise ValueError('Invalid development pilot run.')
    evidence_path = LOG_DIR / 'evidence' / f'{run_id}.json'
    if evidence_path.exists() or (LOG_DIR / f'{run_id}.jsonl').exists():
        raise FileExistsError(f'Pilot run already exists: {run_id}')
    outputs = [_call(run_id, 'schema')]
    if approach == 'B':
        for table in outputs[0]['result']['tables']:
            for column in table['columns']:
                outputs.append(_call(run_id, 'profile', table['name'], column['name']))
    evidence = {
        'workflow': 'codex_proxy',
        'split': 'development',
        'approach': approach,
        'run_id': run_id,
        'source_call_count': len(outputs),
        'source_outputs': outputs,
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open('x', encoding='utf-8') as handle:
        json.dump(evidence, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return evidence_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('approach', choices=['B', 'C'])
    args = parser.parse_args()
    print(prepare(args.run_id, args.approach))


if __name__ == '__main__':
    main()
