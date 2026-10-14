"""Run the explicit seven-rule development baseline on downloaded Sakila.

No model calls or production data access. Reports contain counts and hashes;
raw rows are hashed locally and discarded. This is integration evidence only.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from governance.evaluation import run_baseline
from governance.source import MySQLSource, _json_id
from scripts.public_mysql import DATADIR


def fingerprint(source):
    digest = hashlib.sha256()
    for table in sorted(source.get_schema()['tables'], key=lambda t: t['name']):
        # Identifiers have already passed the adapter's schema validation.
        with source.connection.cursor() as cursor:
            cursor.execute(f'SELECT * FROM `sakila`.`{table["name"]}`')
            encoded = [
                json.dumps(
                    _json_id(row), sort_keys=True, separators=(',', ':'), allow_nan=False
                ).encode()
                for row in cursor.fetchall()
            ]
        digest.update(table['name'].encode() + b'\0')
        for row in sorted(encoded):
            digest.update(len(row).to_bytes(8, 'big') + row)
    return digest.hexdigest()


def main():
    load_dotenv(ROOT / 'data/public-mysql/reader.env', override=True)
    source = MySQLSource.from_env()
    try:
        with source.connection.cursor() as cursor:
            cursor.execute('SELECT @@datadir AS datadir, VERSION() AS version')
            server = cursor.fetchone()
        if Path(server['datadir']).resolve() != DATADIR.resolve() or source.database != 'sakila':
            raise RuntimeError(
                'This probe is restricted to the isolated downloaded Sakila database.'
            )
        schema = source.get_schema()
        before = fingerprint(source)
        baseline = json.loads((ROOT / 'evaluation/sakila/baseline.json').read_text())
        result = run_baseline(source, baseline)
        profiles = []
        for table in schema['tables']:
            for column in table['columns']:
                target = {'table': table['name'], 'column': column['name']}
                profiles.append(source.run_metric('profile', target))
        after = fingerprint(source)
        if before != after:
            raise RuntimeError('Source data changed during the read-only probe.')
        if any(r['status'] != 'completed' for r in result['results']):
            raise RuntimeError('A baseline rule did not complete.')
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'kind': 'public_dataset_integration_test',
            'provider_called': False,
            'research_evaluation': False,
            'reference_reviewed': False,
            'dataset': json.loads((ROOT / 'data/public-mysql/provenance.json').read_text()),
            'schema': schema,
            'profiled_columns': len(profiles),
            'source_hash_before': before,
            'source_hash_after': after,
            'source_unchanged': before == after,
            'baseline': result,
            'note': 'Developer-authored test rules. No model accuracy or human approval is implied.',
        }
        destination = ROOT / 'data/public-mysql/clean-check-report.json'
        destination.write_text(
            json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8'
        )
        print(
            json.dumps(
                {
                    'tables': len(schema['tables']),
                    'columns_profiled': len(profiles),
                    'relationships': len(schema['relationships']),
                    'rows': sum(t['row_count'] for t in schema['tables']),
                    'checks': len(result['results']),
                    'violations': sum(r['violations'] for r in result['results']),
                    'source_unchanged': before == after,
                    'report': str(destination),
                },
                indent=2,
            )
        )
    finally:
        source.close()


if __name__ == '__main__':
    main()
