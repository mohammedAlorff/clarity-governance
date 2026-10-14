"""Repeatable seven-metric technical probe on a separate public-Sakila copy.

Run ``python -m scripts.public_data_faults setup`` once, then ``verify``.
Only the downloaded project instance accepted by public_mysql.connect is used.
These machine-authored injected faults are development checks, not held-out,
human-reviewed or model performance evidence. Setup never replaces a schema.
"""

import argparse
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from dotenv import dotenv_values, set_key

from governance.evaluation import detection_metrics, run_baseline
from governance.source import MySQLSource
from scripts.public_mysql import DATADIR, LAB, PORT, ROOT, connect

SCHEMA = 'sakila_faults'
USER = 'sakila_fault_reader'
ENV = LAB / 'fault-reader.env'
STATE = LAB / 'fault-fixture.json'
CONFIG = ROOT / 'evaluation' / 'sakila'
REPORT = LAB / 'fault-check-report.json'
COLUMNS = {
    'actor': ('actor_id', 'first_name', 'last_name'),
    'film': ('film_id', 'title', 'rental_rate', 'rating'),
    'inventory': ('inventory_id', 'film_id'),
    'rental': ('rental_id', 'rental_date', 'return_date'),
}


def dump(value, path):
    path.write_text(
        json.dumps(value, indent=2, default=str, allow_nan=False) + '\n', encoding='utf-8'
    )


def snapshot(connection, schema):
    """Digest exactly the public rows/columns cloned by this fixture."""
    data = {}
    with connection.cursor() as cursor:
        for table, columns in COLUMNS.items():
            names = ','.join('`' + column + '`' for column in columns)
            cursor.execute(
                f'SELECT {names} FROM `{schema}`.`{table}` ORDER BY `{columns[0]}` LIMIT 11'
            )
            rows = cursor.fetchall()
            if len(rows) < 10 or schema == SCHEMA and len(rows) != 10:
                raise RuntimeError('Unexpected fixture/public row population; no data was reset.')
            data[table] = rows[:10]
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def setup():
    connection = connect()  # Verifies the isolated @@datadir before any mutation.
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME=%s', (SCHEMA,)
            )
            exists = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM mysql.user WHERE User=%s', (USER,))
            if exists or cursor.fetchone()[0] or ENV.exists() or STATE.exists():
                raise RuntimeError(
                    'Fixture/schema/account already exists. Use verify; setup never replaces it.'
                )
        original_digest = snapshot(connection, 'sakila')
        # Retain public identifiers and selected public fields. Nullable names,
        # signed IDs/rates and a text rating intentionally relax constraints so
        # bad data can be represented without weakening the original schema.
        with connection.cursor() as cursor:
            cursor.execute(
                'CREATE DATABASE sakila_faults CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'
            )
            cursor.execute(
                'CREATE TABLE sakila_faults.actor (actor_id INT PRIMARY KEY, first_name VARCHAR(45) NULL, last_name VARCHAR(45) NULL)'
            )
            cursor.execute(
                'CREATE TABLE sakila_faults.film (film_id INT PRIMARY KEY, title VARCHAR(128) NULL, rental_rate DECIMAL(4,2) NULL, rating VARCHAR(10) NULL)'
            )
            cursor.execute(
                'CREATE TABLE sakila_faults.inventory (inventory_id INT PRIMARY KEY, film_id INT NULL)'
            )
            cursor.execute(
                'CREATE TABLE sakila_faults.rental (rental_id INT PRIMARY KEY, rental_date DATETIME NULL, return_date DATETIME NULL)'
            )
            for table, columns in COLUMNS.items():
                names = ','.join('`' + column + '`' for column in columns)
                cursor.execute(
                    f'INSERT INTO sakila_faults.`{table}` ({names}) SELECT {names} FROM sakila.`{table}` ORDER BY `{columns[0]}` LIMIT 10'
                )
            cursor.execute('UPDATE sakila_faults.actor SET first_name=NULL WHERE actor_id=1')
            cursor.execute("UPDATE sakila_faults.actor SET last_name='123' WHERE actor_id=2")
            cursor.execute('SELECT title FROM sakila_faults.film WHERE film_id=1')
            first_title = cursor.fetchone()[0]
            cursor.execute('UPDATE sakila_faults.film SET title=%s WHERE film_id=2', (first_title,))
            cursor.execute('UPDATE sakila_faults.film SET rental_rate=-1 WHERE film_id=3')
            cursor.execute("UPDATE sakila_faults.film SET rating='INVALID' WHERE film_id=4")
            cursor.execute(
                'UPDATE sakila_faults.rental SET return_date=DATE_SUB(rental_date, INTERVAL 1 DAY) WHERE rental_id=1'
            )
            cursor.execute('UPDATE sakila_faults.inventory SET film_id=-1 WHERE inventory_id=1')
            password = secrets.token_hex(24)
            cursor.execute(
                "CREATE USER 'sakila_fault_reader'@'127.0.0.1' IDENTIFIED BY %s", (password,)
            )
            cursor.execute("GRANT SELECT ON sakila_faults.* TO 'sakila_fault_reader'@'127.0.0.1'")
        if snapshot(connection, 'sakila') != original_digest:
            raise RuntimeError('The original source snapshot changed during setup.')
        fixture_digest = snapshot(connection, SCHEMA)
        reader = {
            'MYSQL_HOST': '127.0.0.1',
            'MYSQL_PORT': str(PORT),
            'MYSQL_DATABASE': SCHEMA,
            'MYSQL_USER': USER,
            'MYSQL_PASSWORD': password,
            'MYSQL_ALLOWED_TABLES': '',
            'MYSQL_QUERY_TIMEOUT_MS': '5000',
            'MYSQL_CONNECT_TIMEOUT': '5',
        }
        ENV.touch(exist_ok=False)
        for key, value in reader.items():
            set_key(str(ENV), key, value)
        dump(
            {
                'fixture_version': 1,
                'schema': SCHEMA,
                'copied_source_rows_sha256': original_digest,
                'fixture_rows_sha256': fixture_digest,
                'row_counts': {table: 10 for table in COLUMNS},
                'purpose': 'Machine-authored injected development fixture; not research evidence.',
            },
            STATE,
        )
    finally:
        connection.close()


def verify():
    state = json.loads(STATE.read_text(encoding='utf-8'))
    connection = connect()
    try:
        if state.get('fixture_version') != 1 or state.get('schema') != SCHEMA:
            raise RuntimeError('Unknown fixture state; refusing to verify an unrelated schema.')
        if snapshot(connection, 'sakila') != state['copied_source_rows_sha256']:
            raise RuntimeError('Original public source snapshot changed; review before rerunning.')
        if snapshot(connection, SCHEMA) != state['fixture_rows_sha256']:
            raise RuntimeError('Fixture changed; verification never resets or reinjects faults.')
    finally:
        connection.close()
    values = dotenv_values(ENV)
    if (
        values.get('MYSQL_HOST') != '127.0.0.1'
        or values.get('MYSQL_PORT') != str(PORT)
        or values.get('MYSQL_DATABASE') != SCHEMA
        or values.get('MYSQL_USER') != USER
    ):
        raise RuntimeError('Unexpected reader target; refusing to connect.')
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
            raise RuntimeError('Reader target is outside the isolated public-data lab.')
    source = MySQLSource(reader, SCHEMA)
    try:
        baseline = json.loads((CONFIG / 'fault-baseline.json').read_text(encoding='utf-8'))
        reference = json.loads(
            (CONFIG / 'fault-reference.machine-draft.json').read_text(encoding='utf-8')
        )
        result = run_baseline(source, baseline)
        metrics = detection_metrics(result['detections'], reference['detections'])
        negatives = []
        targets = {
            rule['rule_id']: rule['target']['table'] + '.' + rule['target']['column']
            for rule in baseline['rules']
        }
        for rule_id, rows in reference['expected_clean_row_ids'].items():
            negatives.extend(
                {'rule_id': rule_id, 'row_id': row, 'target': targets[rule_id]} for row in rows
            )
        negative_matches = detection_metrics(result['detections'], negatives)['tp']
        checks = {
            'all_seven_metrics_completed': len(result['results']) == 7
            and all(item['status'] == 'completed' for item in result['results']),
            'all_populations_have_ten_rows': all(
                item['eligible'] == 10 for item in result['results']
            ),
            'all_injected_detections_found': metrics['tp'] == 8
            and metrics['fp'] == 0
            and metrics['fn'] == 0,
            'all_clean_controls_passed': len(negatives) == 62 and negative_matches == 0,
            'original_public_rows_unchanged': True,
        }
        output = {
            'purpose': reference['purpose'],
            'reference_reviewed': False,
            'provider_calls': 0,
            'schema': SCHEMA,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'checks': checks,
            'passed': all(checks.values()),
            'metrics': metrics,
            'clean_controls': {'count': len(negatives), 'incorrectly_flagged': negative_matches},
            'fixture': state,
            'baseline_result': result,
        }
        dump(output, REPORT)
        print(
            json.dumps(
                {
                    'passed': output['passed'],
                    'metrics': metrics,
                    'clean_controls': output['clean_controls'],
                    'report': str(REPORT),
                },
                indent=2,
            )
        )
        if not output['passed']:
            raise RuntimeError('Public-data technical fault probe failed; inspect its report.')
        return output
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'verify'))
    args = parser.parse_args()
    if args.action == 'setup':
        setup()
    verify()


if __name__ == '__main__':
    main()
