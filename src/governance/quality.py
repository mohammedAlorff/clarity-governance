"""Validated, deterministic rule definitions and score aggregation.

Within a dimension, scores weight eligible row-checks equally. Overall scores
weight available dimensions equally. Coverage counts scored checks out of all
applicable checks; a failure or an empty population never implies a pass.
"""

import math
import re
from copy import deepcopy
from datetime import date, datetime

DIMENSIONS = ('completeness', 'uniqueness', 'validity', 'consistency')
METRIC_DIMENSIONS = {
    'profile': None,
    'completeness': 'completeness',
    'uniqueness': 'uniqueness',
    'range': 'validity',
    'allowed_values': 'validity',
    'pattern': 'validity',
    'column_compare': 'consistency',
    'referential': 'consistency',
}
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('Invalid database identifier')
    return value


def type_family(data_type):
    kind = str(data_type).lower().split('(')[0].strip()
    if kind in (
        'int',
        'integer',
        'bigint',
        'smallint',
        'mediumint',
        'tinyint',
        'decimal',
        'numeric',
        'float',
        'double',
        'real',
    ):
        return 'number'
    if kind in ('date', 'datetime', 'timestamp', 'time'):
        return 'date'
    if kind in (
        'char',
        'varchar',
        'text',
        'tinytext',
        'mediumtext',
        'longtext',
        'enum',
        'set',
        'string',
    ):
        return 'string'
    return 'other'


def _column(schema, table, column):
    identifier(table)
    identifier(column)
    for table_info in schema.get('tables', []):
        if table_info['name'] == table:
            for column_info in table_info['columns']:
                if column_info['name'] == column:
                    return column_info
    raise ValueError('Target is not in the permitted schema')


def _number(value):
    try:
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    except OverflowError:
        return False


def _bound(value, family):
    if family == 'number' and _number(value):
        return value
    if family == 'date' and isinstance(value, str) and len(value) <= 32:
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            try:
                date.fromisoformat(value)
                return value
            except ValueError:
                pass
    raise ValueError('Range bounds must match the column type')


def pattern_tokens(pattern):
    """Parse a common regular-expression subset into character predicates.

    Groups, alternation, assertions and backreferences are unsupported. Each
    token matches one character, optionally repeated. Matching uses dynamic
    programming rather than Python's backtracking regex engine.
    """
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= 256:
        raise ValueError('Pattern must contain 1 to 256 characters')
    if any(char in pattern for char in ('(', ')', '|')) or re.search(r'\\[1-9]', pattern):
        raise ValueError('Pattern groups, alternation and backreferences are unsupported')
    body = pattern[1:] if pattern.startswith('^') else pattern
    if body.endswith('$') and not body.endswith(r'\$'):
        body = body[:-1]
    tokens = []
    index = 0
    while index < len(body):
        start = index
        if body[index] == '[':
            index += 1
            if index < len(body) and body[index] == '^':
                index += 1
            if index < len(body) and body[index] == ']':
                index += 1
            while index < len(body) and body[index] != ']':
                index += 2 if body[index] == '\\' else 1
            if index >= len(body):
                raise ValueError('Unclosed character class')
            index += 1
        elif body[index] == '\\':
            if index + 1 >= len(body) or body[index + 1] not in r'dDsSwW\.^$*+?{}[]-@/':
                raise ValueError('Unsupported pattern escape')
            index += 2
        elif body[index] in '^$*+?{}().':
            raise ValueError('Unsupported pattern syntax')
        else:
            index += 1
        token = body[start:index]
        if token.startswith('[') and re.search(r'\\[DSW]', token):
            raise ValueError('Complement escapes inside classes are unsupported')
        minimum = maximum = 1
        if index < len(body) and body[index] in '*+?':
            quantifier = body[index]
            minimum = 1 if quantifier == '+' else 0
            maximum = 1 if quantifier == '?' else 512
            index += 1
        elif index < len(body) and body[index] == '{':
            match = re.match(r'\{(\d{1,3})(?:,(\d{0,3}))?\}', body[index:])
            if not match:
                raise ValueError('Unsupported repetition bound')
            minimum = int(match[1])
            maximum = minimum if match[2] is None else int(match[2]) if match[2] else 512
            if not 0 <= minimum <= maximum <= 512:
                raise ValueError('Repetition bounds must be from 0 to 512')
            index += len(match[0])
        try:
            predicate = re.compile(token, re.ASCII)
        except re.error:
            raise ValueError('Invalid character pattern') from None
        tokens.append((predicate, minimum, maximum, body[start:index]))
    if not tokens:
        raise ValueError('Pattern must match a character')
    return tokens


def matches_pattern(pattern, value):
    """Full match with O(pattern length * bounded input length) computation."""
    if len(value) > 512:
        return False
    reachable = [True] + [False] * len(value)
    for predicate, minimum, maximum, _ in pattern_tokens(pattern):
        prefix = [0]
        for previous in reachable:
            prefix.append(prefix[-1] + int(previous))
        next_reachable = [False] * (len(value) + 1)
        run_start = 0
        for end in range(len(value) + 1):
            if end and not predicate.fullmatch(value[end - 1]):
                run_start = end
            low = max(run_start, end - maximum)
            high = end - minimum
            next_reachable[end] = high >= low and prefix[high + 1] > prefix[low]
        reachable = next_reachable
    return reachable[-1]


def mysql_pattern(pattern):
    # Match the ASCII escapes supported by the local matcher with explicit
    # character classes, avoiding engine-specific POSIX/ICU escape meanings.
    translated = []
    classes = {'d': '0-9', 'w': 'A-Za-z0-9_', 's': ' \t\n\r\f\v'}
    for _, _, _, token in pattern_tokens(pattern):
        if token.startswith('['):
            for escape, chars in classes.items():
                token = token.replace('\\' + escape, chars)
        else:
            for escape, chars in classes.items():
                token = token.replace('\\' + escape, '[' + chars + ']').replace(
                    '\\' + escape.upper(), '[^' + chars + ']'
                )
        translated.append(token)
    return '^' + ''.join(translated) + '$'


def validate_rule(rule, schema):
    """Return a detached canonical rule, rejecting all unrecognized options."""
    if not isinstance(rule, dict) or set(rule) - {'metric_id', 'target', 'parameters'}:
        raise ValueError('Rule must contain only metric_id, target and parameters')
    metric = rule.get('metric_id')
    if not isinstance(metric, str) or metric not in METRIC_DIMENSIONS:
        raise ValueError('Unsupported metric')
    target = rule.get('target')
    if not isinstance(target, dict) or set(target) != {'table', 'column'}:
        raise ValueError('Target must specify table and column')
    info = _column(schema, target['table'], target['column'])
    family = type_family(info['data_type'])
    params = rule.get('parameters', {})
    if not isinstance(params, dict):
        raise ValueError('Parameters must be an object')
    accepted = {
        'profile': set(),
        'completeness': set(),
        'uniqueness': set(),
        'range': {'min', 'max'},
        'allowed_values': {'values'},
        'pattern': {'pattern'},
        'column_compare': {'other_column', 'operator'},
        'referential': {'reference_table', 'reference_column'},
    }[metric]
    if set(params) - accepted:
        raise ValueError('Unsupported metric parameter')
    if metric == 'range':
        if family not in ('number', 'date') or not params:
            raise ValueError('Range requires a numeric/date column and a bound')
        for key, value in params.items():
            _bound(value, family)
        if 'min' in params and 'max' in params and params['min'] > params['max']:
            raise ValueError('Minimum exceeds maximum')
    elif metric == 'allowed_values':
        values = params.get('values')
        if not isinstance(values, list) or not 1 <= len(values) <= 100:
            raise ValueError('Allowed values requires 1 to 100 scalar values')
        for value in values:
            if (
                value is None
                or not isinstance(value, (str, int, float, bool))
                or isinstance(value, str)
                and len(value) > 256
            ):
                raise ValueError('Allowed values must be bounded non-null scalars')
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and not _number(value)
            ):
                raise ValueError('Allowed values must be finite')
            if family == 'number' and not _number(value):
                raise ValueError('Allowed values must match the column type')
            if family == 'string' and not isinstance(value, str):
                raise ValueError('Allowed values must match the column type')
            if family == 'date':
                _bound(value, family)
            if family == 'other':
                raise ValueError('Allowed values column type is unsupported')
    elif metric == 'pattern':
        if family != 'string' or set(params) != {'pattern'}:
            raise ValueError('Pattern requires a text column and pattern')
        pattern_tokens(params['pattern'])
    elif metric == 'column_compare':
        if set(params) != accepted or params['operator'] not in ('=', '!=', '<', '<=', '>', '>='):
            raise ValueError('Comparison requires another column and supported operator')
        other = _column(schema, target['table'], params['other_column'])
        if family != type_family(other['data_type']) or family == 'other':
            raise ValueError('Comparison columns must have compatible types')
    elif metric == 'referential':
        if set(params) != accepted:
            raise ValueError('Reference requires table and column')
        other = _column(schema, params['reference_table'], params['reference_column'])
        if family != type_family(other['data_type']) or family == 'other':
            raise ValueError('Reference columns must have compatible types')
    return deepcopy({'metric_id': metric, 'target': target, 'parameters': params})


def summarize_results(results):
    dimensions = {}
    total_completed = total_applicable = 0
    for dimension in DIMENSIONS:
        checks = [
            r
            for r in results
            if r.get('dimension') == dimension and r.get('metric_id') != 'profile'
        ]
        applicable = [r for r in checks if r.get('status') != 'not_applicable']
        completed = [
            r for r in applicable if r.get('status') == 'completed' and r.get('eligible', 0) > 0
        ]
        eligible = sum(r['eligible'] for r in completed)
        passing = sum(r.get('passing', 0) for r in completed)
        violations = sum(
            r.get('violations', r['eligible'] - r.get('passing', 0)) for r in completed
        )
        score = round(100 * passing / eligible, 2) if eligible else None
        status = (
            'unavailable'
            if not completed
            else 'complete'
            if len(completed) == len(applicable)
            else 'partial'
        )
        dimensions[dimension] = {
            'score': score,
            'status': status,
            'eligible': eligible,
            'passing': passing,
            'violations': violations,
            'completed_checks': len(completed),
            'applicable_checks': len(applicable),
            'coverage': len(completed) / len(applicable) if applicable else None,
        }
        total_completed += len(completed)
        total_applicable += len(applicable)
    scores = [d['score'] for d in dimensions.values() if d['score'] is not None]
    return {
        'overall_score': round(sum(scores) / len(scores), 2) if scores else None,
        'status': 'unavailable'
        if not scores
        else 'complete'
        if total_completed == total_applicable
        else 'partial',
        'coverage': total_completed / total_applicable if total_applicable else None,
        'dimensions': dimensions,
        'completed_checks': total_completed,
        'applicable_checks': total_applicable,
    }
