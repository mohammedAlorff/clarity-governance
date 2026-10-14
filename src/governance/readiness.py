"""Local preflight using cached metadata; no source queries or provider requests."""

from dataclasses import asdict

from .contracts import RunLimits
from .providers import model_settings
from .sampling import SamplingPolicy


def inspection_readiness(schema, source_mode, mode, limits=None, *, source_connected=True):
    if mode not in {'demo', 'fixed', 'agent'}:
        raise ValueError('Unknown inspection mode.')
    limits = limits or RunLimits()
    issues = []

    def issue(code, message):
        issues.append({'code': code, 'message': message})

    if not schema or not source_mode or not source_connected:
        issue('source_disconnected', 'Connect a source before inspecting.')
    elif mode == 'demo' and source_mode != 'demo':
        issue('source_mode', 'Synthetic inspection is available only for the demo source.')
    columns = sum(len(table['columns']) for table in (schema or {}).get('tables', []))
    required = columns + 1 if schema else None
    if mode in {'demo', 'fixed'} and required and limits.max_calls < required:
        issue(
            'fixed_call_budget', f'This full profiling pass needs at least {required} tool calls.'
        )
    provider, model = 'synthetic', 'deterministic-demo-v1'
    if mode != 'demo':
        provider, model = None, None
        try:
            settings = model_settings()
            provider, model = settings['provider'], settings['model']
            if not settings['configured']:
                fields = ' and '.join(filter(None, (settings['key_env'], settings['model_env'])))
                issue(
                    'provider_configuration',
                    f'Configure {fields} locally.',
                )
        except ValueError as exc:
            issue('provider_configuration', str(exc))
    try:
        sampling = asdict(SamplingPolicy.from_env())
    except ValueError:
        sampling = None
        issue('privacy', 'Correct the local privacy sampling configuration before inspecting.')
    return {
        'ready': not issues,
        'issues': issues,
        'mode': mode,
        'columns': columns,
        'profile_calls_required': required,
        'limits': asdict(limits),
        'provider': provider,
        'model': model,
        'provider_verified': False,
        'sampling': sampling,
        'note': 'Local configuration check only. Credentials, model access, source freshness, '
        'and sufficient time or tokens are not verified. No provider request was sent.',
    }
