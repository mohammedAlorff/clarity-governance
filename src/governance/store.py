"""Transactional application storage. No source-database writes occur here."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scopes (
                    id TEXT PRIMARY KEY, mode TEXT NOT NULL, name TEXT NOT NULL,
                    created_at TEXT NOT NULL, schema_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL, lineage TEXT NOT NULL,
                    version INTEGER NOT NULL, current INTEGER NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL, original TEXT NOT NULL,
                    created_at TEXT NOT NULL, reviewer TEXT, reviewed_at TEXT,
                    UNIQUE(lineage, version));
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, proposal TEXT NOT NULL, action TEXT NOT NULL,
                    reviewer TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
                    review_seconds REAL);
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL);
            """)
            if 'review_seconds' not in {
                r['name'] for r in db.execute('PRAGMA table_info(reviews)')
            }:
                db.execute('ALTER TABLE reviews ADD COLUMN review_seconds REAL')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def new_scope(self, mode, name, schema=None):
        sid = uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                'INSERT INTO scopes VALUES(?,?,?,?,?)',
                (sid, mode, name, now(), json.dumps(schema or {})),
            )
        return sid

    def latest_scope(self):
        with self.connection() as db:
            row = db.execute('SELECT * FROM scopes ORDER BY rowid DESC LIMIT 1').fetchone()
            return dict(row) if row else None

    def add_proposal(self, scope, proposal):
        pid = uuid.uuid4().hex
        status = proposal.get('status', 'draft')
        if status not in ('draft', 'needs_clarification'):
            raise ValueError('New proposals must be drafts or need clarification.')
        payload = json.dumps(proposal)
        with self.connection() as db:
            db.execute(
                'INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (pid, scope, pid, 1, 1, status, payload, payload, now(), None, None),
            )
        return self.get_proposal(pid)

    def _decode(self, db, row, history=True):
        p = json.loads(row['payload'])
        p.update(
            id=row['id'],
            scope=row['scope'],
            lineage_id=row['lineage'],
            version=row['version'],
            current=bool(row['current']),
            status=row['status'],
            created_at=row['created_at'],
            reviewer=row['reviewer'],
            reviewed_at=row['reviewed_at'],
            original=json.loads(row['original']),
        )
        p['history'] = []
        if history:
            for v in db.execute(
                'SELECT * FROM proposals WHERE lineage=? ORDER BY version', (row['lineage'],)
            ):
                entry = self._decode(db, v, False)
                entry.pop('history')
                entry.pop('original')
                entry['reviews'] = [
                    dict(r)
                    for r in db.execute(
                        'SELECT action,reviewer,note,created_at,review_seconds FROM reviews WHERE proposal=? ORDER BY id',
                        (v['id'],),
                    )
                ]
                p['history'].append(entry)
        return p

    def get_proposal(self, pid):
        with self.connection() as db:
            row = db.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
            if not row:
                raise KeyError('Proposal not found.')
            return self._decode(db, row)

    def proposals(self, scope):
        with self.connection() as db:
            return [
                self._decode(db, r)
                for r in db.execute(
                    'SELECT * FROM proposals WHERE scope=? AND current=1 ORDER BY rowid', (scope,)
                )
            ]

    def approved_rules(self, scope):
        return [
            p for p in self.proposals(scope) if p['kind'] == 'rule' and p['status'] == 'approved'
        ]

    def review(self, pid, action, reviewer, note='', changes=None, review_seconds=None):
        reviewer = reviewer.strip()
        if not reviewer or len(reviewer) > 100:
            raise ValueError('Enter a reviewer name of 1–100 characters.')
        if action not in ('approve', 'reject', 'clarify', 'edit'):
            raise ValueError('Unknown review action.')
        if len(note) > 2000:
            raise ValueError('Review note is too long.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
            if not row:
                raise KeyError('Proposal not found.')
            if not row['current']:
                raise Conflict('This version was superseded. Refresh the review queue.')
            if action != 'edit' and row['status'] not in ('draft', 'needs_clarification'):
                raise Conflict('This version is already reviewed. Edit it to create a new draft.')
            if action == 'approve' and row['status'] == 'needs_clarification':
                raise Conflict('Resolve the missing evidence with an edit before approval.')
            stamp = now()
            if action == 'edit':
                allowed = {'title', 'description', 'evidence', 'assumptions', 'rule'}
                changes = changes or {}
                if not changes or set(changes) - allowed:
                    raise ValueError('An edit must contain supported proposal fields.')
                payload = json.loads(row['payload'])
                payload.update(changes)
                payload['status'] = 'draft'
                new_id = uuid.uuid4().hex
                db.execute('UPDATE proposals SET current=0 WHERE id=?', (pid,))
                db.execute(
                    'INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        new_id,
                        row['scope'],
                        row['lineage'],
                        row['version'] + 1,
                        1,
                        'draft',
                        json.dumps(payload),
                        row['original'],
                        stamp,
                        None,
                        None,
                    ),
                )
            else:
                new_id = pid
                status = {
                    'approve': 'approved',
                    'reject': 'rejected',
                    'clarify': 'needs_clarification',
                }[action]
                db.execute(
                    'UPDATE proposals SET status=?, reviewer=?, reviewed_at=? WHERE id=?',
                    (status, reviewer, stamp, pid),
                )
            db.execute(
                'INSERT INTO reviews(proposal,action,reviewer,note,created_at,review_seconds) VALUES(?,?,?,?,?,?)',
                (pid, action, reviewer, note, stamp, review_seconds),
            )
        return self.get_proposal(new_id)

    def add_record(self, scope, kind, payload):
        rid = uuid.uuid4().hex
        record = {**payload, 'id': rid, 'created_at': now()}
        with self.connection() as db:
            db.execute(
                'INSERT INTO records VALUES(?,?,?,?,?)',
                (rid, scope, kind, record['created_at'], json.dumps(record)),
            )
        return record

    def records(self, scope, kind):
        with self.connection() as db:
            return [
                json.loads(row['payload'])
                for row in db.execute(
                    'SELECT payload FROM records WHERE scope=? AND kind=? ORDER BY rowid DESC',
                    (scope, kind),
                )
            ]
