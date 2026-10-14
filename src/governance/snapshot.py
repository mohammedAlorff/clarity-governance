"""Bounded, order-independent content fingerprints; raw rows never leave memory."""

import hashlib
import json
import time

MAX_SNAPSHOT_ROWS = 1_000_000
MAX_SNAPSHOT_SECONDS = 300
MAX_ROW_BYTES = 1_000_000
_MODULUS = 1 << 256


class SnapshotDigest:
    """Hash a multiset of rows without retaining or disclosing source values."""

    def __init__(self):
        self.started = time.monotonic()
        self.total_rows = 0
        self.tables = []

    def add_table(self, name, rows):
        from .source import _json_id

        count = 0
        row_sum = 0
        row_xor = 0
        for row in rows:
            self.total_rows += 1
            count += 1
            if (
                self.total_rows > MAX_SNAPSHOT_ROWS
                or time.monotonic() - self.started > MAX_SNAPSHOT_SECONDS
            ):
                raise RuntimeError('Source snapshot exceeded its row or time limit.')
            encoded = json.dumps(
                _json_id(row), sort_keys=True, separators=(',', ':'), allow_nan=False
            ).encode('utf-8')
            if len(encoded) > MAX_ROW_BYTES:
                raise RuntimeError('A source row exceeded the snapshot size limit.')
            number = int.from_bytes(hashlib.sha256(encoded).digest(), 'big')
            row_sum = (row_sum + number) % _MODULUS
            row_xor ^= number
        self.tables.append(
            {'name': name, 'rows': count, 'sum': f'{row_sum:064x}', 'xor': f'{row_xor:064x}'}
        )

    def hexdigest(self):
        payload = json.dumps(
            {'algorithm': 'row-multiset-sha256-v1', 'tables': self.tables},
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()
