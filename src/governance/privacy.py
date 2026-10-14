"""Conservative outbound projection: schema, aggregate counts, and shapes only.

This is an allowlist, rather than a blacklist of possible credential field names.
Unknown fields, raw samples, source comments, errors and violation IDs never leave
the process. Identifiers are metadata and remain visible if simple and bounded.
"""

import math
import re
from dataclasses import asdict

from .sampling import LENGTH_BUCKETS, SamplingPolicy, length_bucket

_IDENTIFIERS = {
    'name',
    'table',
    'column',
    'other_column',
    'reference_table',
    'reference_column',
    'from_table',
    'from_column',
    'to_table',
    'to_column',
    'referenced_table',
    'referenced_column',
}
_COUNTS = {
    'row_count',
    'null_count',
    'non_null_count',
    'distinct_count',
    'eligible',
    'passing',
    'violations',
    'sample_count',
    'length',
    'count',
}
_CONTAINERS = {'tables', 'columns', 'relationships', 'target', 'schema', 'profiles', 'shapes'}
_ENUMS = {
    'metric_id': {
        'profile',
        'completeness',
        'uniqueness',
        'range',
        'allowed_values',
        'pattern',
        'column_compare',
        'referential',
    },
    'status': {'completed', 'not_applicable', 'not_run', 'failed', 'no_eligible_data', 'blocked'},
    'dimension': {'completeness', 'uniqueness', 'validity', 'consistency'},
    'type': {'string', 'number', 'null', 'boolean', 'date'},
    'key': {'PRI', 'MUL', 'UNI', 'primary', 'foreign', 'unique', ''},
    'length_bucket': set(LENGTH_BUCKETS),
}
_TYPES = {
    'varchar',
    'char',
    'text',
    'tinytext',
    'mediumtext',
    'longtext',
    'integer',
    'int',
    'bigint',
    'smallint',
    'tinyint',
    'mediumint',
    'decimal',
    'numeric',
    'float',
    'double',
    'real',
    'boolean',
    'bool',
    'date',
    'datetime',
    'timestamp',
    'time',
    'year',
    'json',
    'binary',
    'varbinary',
    'blob',
    'enum',
    'set',
}
_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')


def model_view(value, *, max_items=100, _depth=0, _budget=None):
    """Return a fresh JSON-compatible, bounded projection of source output."""
    if _budget is None:
        _budget = [2000]
    if _depth > 8 or _budget[0] <= 0:
        return None
    if isinstance(value, list):
        result = []
        for item in value[:max_items]:
            if _budget[0] <= 0:
                break
            if isinstance(item, (dict, list)):
                result.append(
                    model_view(item, max_items=max_items, _depth=_depth + 1, _budget=_budget)
                )
        return result
    if not isinstance(value, dict):
        return None
    result = {}
    for key, item in list(value.items())[:200]:
        if _budget[0] <= 0:
            break
        _budget[0] -= 1
        if key in _CONTAINERS and isinstance(item, (dict, list)):
            result[key] = model_view(item, max_items=max_items, _depth=_depth + 1, _budget=_budget)
        elif key in _IDENTIFIERS and isinstance(item, str) and _IDENTIFIER_RE.fullmatch(item):
            result[key] = item
        elif key in _COUNTS and isinstance(item, (int, float)) and not isinstance(item, bool):
            if math.isfinite(item) and 0 <= item <= 10**15:
                result[key] = item
        elif key in {'nullable', 'redacted'} and isinstance(item, bool):
            result[key] = item
        elif key in _ENUMS and (item is None or isinstance(item, str) and item in _ENUMS[key]):
            result[key] = item
        elif key == 'data_type' and isinstance(item, str):
            # Deliberately exclude enum literals and column type annotations.
            base = item.lower().split('(')[0].split(' ')[0]
            result[key] = base if base in _TYPES else 'unknown'
    return result


def sample_shapes(value):
    """Keep only already-redacted shape descriptors; never inspect raw values."""
    shapes = []
    if isinstance(value, dict):
        for item in value.get('samples', [])[:10]:
            if isinstance(item, dict) and set(item) <= {'type', 'length', 'length_bucket'}:
                descriptor = dict(item)
                if 'length' in descriptor:
                    try:
                        descriptor['length_bucket'] = length_bucket(descriptor.pop('length'))
                    except ValueError:
                        continue
                shape = model_view(descriptor)
                if 'type' in shape:
                    shapes.append(shape)
    return {'shapes': shapes, 'sample_count': len(shapes), 'redacted': True}


def privacy_report(inspections, provider):
    """Expose policy and observed gate counters, never a fabricated risk score."""
    try:
        sampling = asdict(SamplingPolicy.from_env())
        error = None
    except ValueError:
        sampling = None
        error = 'Invalid privacy sampling configuration. Model inspection is blocked.'
    policy = {
        'version': 'strict-shapes-v1',
        'raw_values_allowed': False,
        'schema_identifiers_visible': True,
        'aggregate_counts_visible': True,
        'sampling': sampling,
        'configuration_error': error,
    }
    runs = []
    legacy = 0
    for inspection in inspections:
        audit = inspection.get('privacy')
        if not isinstance(audit, dict):
            legacy += 1
            continue
        runs.append(
            {
                'id': inspection.get('id'),
                'status': inspection.get('status'),
                'provider': inspection.get('provider'),
                'model': inspection.get('model'),
                'policy_version': audit.get('policy_version'),
                'sampling': audit.get('sampling'),
                **{
                    key: audit.get(key, 0)
                    for key in (
                        'checked_requests',
                        'blocked_requests',
                        'shape_descriptors_submitted',
                    )
                },
            }
        )
    return {
        'policy': policy,
        'provider': provider,
        'runs': runs,
        'checked_requests': sum(run['checked_requests'] for run in runs),
        'blocked_requests': sum(run['blocked_requests'] for run in runs),
        'legacy_runs_without_audit': legacy,
        'accuracy_retention': None,
        'compliance_certified': False,
        'limitations': [
            'Schema identifiers and exact aggregate counts remain visible to the selected provider.',
            'Seeded samples come from a bounded candidate pool and are not population-uniform.',
            'Gate counters measure checks made by this application, not overall disclosure risk.',
            'Masking and sampling do not establish anonymity, regulatory compliance, or model accuracy.',
        ],
    }
