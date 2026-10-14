"""Manage only this project's downloaded, isolated Sakila development server.

Never discovers system MySQL installations or connects to port 3306. Source
bootstrap is a developer operation; the application receives SELECT-only access.
"""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import pymysql
from dotenv import set_key

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'data' / 'public-mysql'
RUNTIME = LAB / 'runtime' / 'mysql-8.4.11-winx64'
# Keep mutable server files outside protected/synchronized Desktop folders.
SERVER = Path(os.environ.get('LOCALAPPDATA', str(ROOT / 'data'))) / 'Clarity' / 'public-mysql'
DATADIR = SERVER / 'server-data'
STATE = LAB / 'private.json'
PORT = 3307
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def credentials():
    return json.loads(STATE.read_text(encoding='utf-8'))


def connect():
    private = credentials()
    conn = pymysql.connect(
        host='127.0.0.1',
        port=PORT,
        user='root',
        password=private['admin_password'],
        connect_timeout=2,
        read_timeout=10,
        autocommit=True,
    )
    with conn.cursor() as cursor:
        cursor.execute('SELECT @@datadir')
        actual = Path(cursor.fetchone()[0]).resolve()
    if actual != DATADIR.resolve():
        conn.close()
        raise RuntimeError('Refusing to manage a database outside the public-data lab.')
    return conn


def running():
    try:
        conn = connect()
        conn.close()
        return True
    except (pymysql.MySQLError, OSError):
        return False


def require_free_port():
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', PORT))
        except OSError:
            raise RuntimeError(
                'Port 3307 is occupied; no existing service will be changed.'
            ) from None


def start(init_file=None):
    if running():
        return
    require_free_port()
    binary = RUNTIME / 'bin' / 'mysqld.exe'
    if not binary.is_file():
        raise RuntimeError(
            'Download and extract the official portable archive first; see docs/public-data-test.md.'
        )
    args = [
        str(binary),
        '--no-defaults',
        '--no-monitor',
        f'--basedir={RUNTIME.as_posix()}',
        f'--datadir={DATADIR.as_posix()}',
        f'--port={PORT}',
        '--bind-address=127.0.0.1',
        '--mysqlx=OFF',
        '--local-infile=OFF',
        '--secure-file-priv=NULL',
        '--skip-log-bin',
        '--innodb-buffer-pool-size=64M',
        f'--log-error={(SERVER / "server.log").as_posix()}',
        f'--pid-file={(SERVER / "server.pid").as_posix()}',
    ]
    if init_file:
        args.append(f'--init-file={init_file.as_posix()}')
    process = subprocess.Popen(
        args,
        cwd=LAB,
        creationflags=FLAGS,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if running():
            return
        if process.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError(
        f'Portable server did not become ready; inspect {SERVER / "server.log"} locally.'
    )


def initialize():
    if DATADIR.exists():
        raise RuntimeError(
            'Lab already exists. Use start; setup never replaces existing database files.'
        )
    binary = RUNTIME / 'bin' / 'mysqld.exe'
    if not binary.is_file():
        raise RuntimeError('Portable MySQL archive is missing; see docs/public-data-test.md.')
    require_free_port()
    SERVER.mkdir(parents=True, exist_ok=True)
    private = (
        credentials()
        if STATE.exists()
        else {'admin_password': secrets.token_hex(24), 'reader_password': secrets.token_hex(24)}
    )
    if not STATE.exists():
        STATE.write_text(json.dumps(private), encoding='utf-8')
    result = subprocess.run(
        [
            str(binary),
            '--no-defaults',
            '--initialize-insecure',
            f'--basedir={RUNTIME.as_posix()}',
            f'--datadir={DATADIR.as_posix()}',
            f'--log-error={(SERVER / "initialization.log").as_posix()}',
        ],
        creationflags=FLAGS,
        capture_output=True,
        timeout=120,
    )
    if result.returncode:
        (LAB / 'initialization-error.log').write_bytes(result.stderr)
        raise RuntimeError('Initialization failed; inspect the private initialization log.')
    # This runs before the new instance accepts client connections. Passwords
    # never enter command arguments, terminal output, or application settings.
    bootstrap = LAB / 'bootstrap.sql'
    bootstrap.write_text(
        "ALTER USER 'root'@'localhost' IDENTIFIED BY '" + private['admin_password'] + "';\n",
        encoding='utf-8',
    )
    start(bootstrap)
    bootstrap.unlink()
    import_dataset()


def import_dataset():
    private = credentials()
    conn = connect()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='sakila'"
        )
        if cursor.fetchone()[0]:
            conn.close()
            raise RuntimeError('Sakila already exists; refusing to replace its data.')
    conn.close()
    config = LAB / 'import-client.cnf'
    config.write_text(
        '[client]\nhost=127.0.0.1\nport=3307\nuser=root\npassword='
        + private['admin_password']
        + '\n',
        encoding='utf-8',
    )
    try:
        for name in ('sakila-schema.sql', 'sakila-data.sql'):
            with (LAB / 'dataset' / 'sakila-db' / name).open('rb') as sql:
                result = subprocess.run(
                    [
                        str(RUNTIME / 'bin' / 'mysql.exe'),
                        f'--defaults-file={config.as_posix()}',
                        '--default-character-set=utf8mb4',
                        '--binary-mode',
                    ],
                    stdin=sql,
                    capture_output=True,
                    creationflags=FLAGS,
                    timeout=120,
                )
            if result.returncode:
                (LAB / 'import-error.log').write_bytes(result.stderr)
                raise RuntimeError('Dataset import failed; inspect the local import-error.log.')
    finally:
        config.unlink(missing_ok=True)
    conn = connect()
    with conn.cursor() as cursor:
        cursor.execute(
            "CREATE USER 'governance_reader'@'127.0.0.1' IDENTIFIED BY %s",
            (private['reader_password'],),
        )
        cursor.execute("GRANT SELECT ON sakila.* TO 'governance_reader'@'127.0.0.1'")
        cursor.execute('SELECT VERSION()')
        version = cursor.fetchone()[0]
    conn.close()
    reader = {
        'MYSQL_HOST': '127.0.0.1',
        'MYSQL_PORT': str(PORT),
        'MYSQL_DATABASE': 'sakila',
        'MYSQL_USER': 'governance_reader',
        'MYSQL_PASSWORD': private['reader_password'],
        'MYSQL_ALLOWED_TABLES': '',
        'MYSQL_QUERY_TIMEOUT_MS': '5000',
        'MYSQL_CONNECT_TIMEOUT': '5',
    }
    env = LAB / 'reader.env'
    env.touch()
    for key, value in reader.items():
        set_key(str(env), key, value)
    provenance = {
        'dataset': 'Sakila',
        'dataset_version': '1.5',
        'server_version': version,
        'dataset_url': 'https://downloads.mysql.com/docs/sakila-db.zip',
        'server_url': 'https://dev.mysql.com/get/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip',
        'dataset_sha256': hashlib.sha256(
            (LAB / 'downloads' / 'sakila-db.zip').read_bytes()
        ).hexdigest(),
        'server_sha256': hashlib.sha256(
            (LAB / 'downloads' / 'mysql-8.4.11-winx64.zip').read_bytes()
        ).hexdigest(),
        'port': PORT,
        'read_only_user': 'governance_reader',
        'purpose': 'Public development dataset; not held-out model evidence.',
    }
    (LAB / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'start', 'stop', 'status'))
    args = parser.parse_args()
    if args.action == 'setup':
        initialize()
    elif args.action == 'start':
        start()
    elif args.action == 'stop':
        if running():
            conn = connect()
            with conn.cursor() as cursor:
                cursor.execute('SHUTDOWN')
            conn.close()
        print('Isolated public-data server stopped; database files retained.')
        return
    print('Isolated Sakila server on 127.0.0.1:3307: ' + ('running' if running() else 'stopped'))


if __name__ == '__main__':
    main()
