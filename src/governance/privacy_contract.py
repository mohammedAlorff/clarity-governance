"""Fail closed on outbound history outside the inspection privacy contract.

Source data must already be projected before reaching this boundary. This
validator rejects changes instead of silently sanitizing them. The first system
message is application-owned trusted text; schema identifiers remain intentional
metadata. Literal checks on model tool arguments supplement that structural
contract and do not claim to identify every possible personal value or secret.
"""

import json
import re

from .privacy import model_view
from .quality import validate_rule

_ERROR = 'Outbound privacy contract validation failed.'
_INSTRUCTIONS = {
    'Fixed workflow inspection is complete. Return final proposals now; no further tools are available.',
    'Response failed validation. Use permitted tools or return a valid proposal object for existing targets.',
}
_RESULT_PREFIX = 'Inspection tool result: '
_CALL_ID = re.compile(r'[A-Za-z0-9_-]{1,100}')
_PARAMETERS = {
    'min',
    'max',
    'values',
    'pattern',
    'other_column',
    'operator',
    'reference_table',
    'reference_column',
}
_IDENTIFIER_PARAMETERS = {'other_column', 'reference_table', 'reference_column'}
_SHAPE_TYPES = {'string', 'number', 'null', 'boolean', 'date'}
_EMAIL = re.compile(r'[A-Za-z0-9.!#$%&\'*+/=?_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+')
_CARD = re.compile(r'(?<![A-Za-z0-9])(?:[0-9][ -]?){12,18}[0-9](?![A-Za-z0-9])')
_CREDENTIAL = re.compile(
    r'(?i)(?:\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{6,}'
    r'|\bAIza[A-Za-z0-9_-]{12,}|\bAKIA[A-Z0-9]{16}'
    r'|-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'
    r'|\bbearer\s+[A-Za-z0-9_.-]{6,}'
    r'|\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*[A-Za-z0-9_./+-]{3,})'
)


class PrivacyViolation(Exception):
    """A generic boundary failure that contains no original payload values."""

    def __init__(self):
        super().__init__(_ERROR)


def _require(condition):
    if not condition:
        raise PrivacyViolation()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_constant(_value):
    raise PrivacyViolation()


def _json(text):
    _require(isinstance(text, str))
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def _shape_count(value):
    if isinstance(value, list):
        return sum(_shape_count(item) for item in value)
    if not isinstance(value, dict):
        return 0
    total = 0
    for key, item in value.items():
        if key == 'shapes':
            _require(isinstance(item, list) and len(item) <= 10)
            _require(value.get('redacted') is True)
            _require(type(value.get('sample_count')) is int and value['sample_count'] == len(item))
            for shape in item:
                _require(isinstance(shape, dict) and set(shape) <= {'type', 'length_bucket'})
                _require(isinstance(shape.get('type'), str) and shape['type'] in _SHAPE_TYPES)
                if 'length_bucket' in shape:
                    _require(isinstance(shape['length_bucket'], str))
            total += len(item)
        else:
            total += _shape_count(item)
    return total


def _source(value):
    _require(isinstance(value, dict) and model_view(value) == value)
    return _shape_count(value)


def _literal_values(value):
    # Numeric aggregates and thresholds are not phone or card literals. Field
    # identifiers are validated against the schema rather than keyword filters.
    if isinstance(value, str):
        _require(not (_EMAIL.search(value) or _CARD.search(value) or _CREDENTIAL.search(value)))
    elif isinstance(value, list):
        for item in value:
            _literal_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            _literal_values(item)


def _arguments(name, arguments, schema):
    _require(isinstance(arguments, dict))
    if name == 'get_schema':
        _require(not arguments)
        return
    _require(isinstance(schema, dict))
    if name == 'sample_column':
        _require(set(arguments) == {'table', 'column', 'limit'})
        _require(type(arguments['limit']) is int and 1 <= arguments['limit'] <= 20)
        # A profile with no parameters checks the same schema target grammar.
        validate_rule(
            {
                'metric_id': 'profile',
                'target': {'table': arguments['table'], 'column': arguments['column']},
                'parameters': {},
            },
            schema,
        )
        return
    _require(name == 'run_metric' and set(arguments) == {'metric_id', 'target', 'parameters'})
    parameters = arguments['parameters']
    _require(isinstance(parameters, dict) and not set(parameters) - _PARAMETERS)
    canonical = {key: value for key, value in parameters.items() if value is not None}
    _require(len(json.dumps(canonical, allow_nan=False)) <= 4000)
    validate_rule(
        {
            'metric_id': arguments['metric_id'],
            'target': arguments['target'],
            'parameters': canonical,
        },
        schema,
    )
    for key, value in canonical.items():
        if key not in _IDENTIFIER_PARAMETERS:
            _literal_values(value)


def validate_messages(messages):
    """Validate canonical provider history and return counts without values.

    The function never rewrites messages. Malformed JSON, unknown message fields,
    unprojected source payloads, raw samples, and unsafe literal tool arguments all
    raise the same generic ``PrivacyViolation`` before a provider request is made.
    """
    try:
        _require(isinstance(messages, list) and bool(messages))
        schema, pending_call, shapes = None, None, 0
        for index, message in enumerate(messages):
            _require(isinstance(message, dict))
            if set(message) == {'role', 'content'}:
                _require(pending_call is None)
                role, content = message['role'], message['content']
                _require(isinstance(content, str))
                if role == 'system':
                    _require(index == 0 and bool(content))
                    continue
                _require(role == 'user')
                if content in _INSTRUCTIONS:
                    continue
                if content.startswith(_RESULT_PREFIX):
                    shapes += _source(_json(content[len(_RESULT_PREFIX) :]))
                    continue
                value = _json(content)
                _require(isinstance(value, dict))
                if set(value) == {'schema'}:
                    _require(schema is None and isinstance(value['schema'], dict))
                    shapes += _source(value)
                    schema = value['schema']
                else:
                    _require(set(value) == {'profiles'} and isinstance(value['profiles'], list))
                    shapes += _source(value)
            elif message.get('type') == 'function_call':
                _require(
                    pending_call is None
                    and set(message) == {'type', 'name', 'arguments', 'call_id'}
                )
                _require(
                    isinstance(message['call_id'], str) and _CALL_ID.fullmatch(message['call_id'])
                )
                _arguments(message['name'], _json(message['arguments']), schema)
                pending_call = message['call_id']
            elif message.get('type') == 'function_call_output':
                _require(set(message) == {'type', 'call_id', 'output'})
                _require(pending_call is not None and message['call_id'] == pending_call)
                shapes += _source(_json(message['output']))
                pending_call = None
            else:
                raise PrivacyViolation()
        _require(pending_call is None)
        return {'checked_messages': len(messages), 'shape_descriptors': shapes}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise PrivacyViolation() from None
