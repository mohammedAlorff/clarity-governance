"""Select a model provider without exposing credentials or silent fallback."""

import os


def model_settings():
    provider = os.getenv('LLM_PROVIDER', 'openai').strip().lower()
    if provider not in {'openai', 'gemini', 'local'}:
        raise ValueError('LLM_PROVIDER must be openai, gemini, or local.')
    if provider == 'local':
        from .local import _local_url

        _local_url(os.getenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:1234/v1').strip())
        model = os.getenv('LOCAL_MODEL', '').strip()
        return {
            'provider': provider,
            'model': model,
            'key_env': '',
            'model_env': 'LOCAL_MODEL',
            'configured': bool(
                model and os.getenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:1234/v1').strip()
            ),
        }
    prefix = provider.upper()
    key_env, model_env = prefix + '_API_KEY', prefix + '_MODEL'
    model = os.getenv(model_env, '').strip()
    return {
        'provider': provider,
        'model': model,
        'key_env': key_env,
        'model_env': model_env,
        'configured': bool(os.getenv(key_env, '').strip() and model),
    }


def create_client():
    settings = model_settings()
    if not settings['configured']:
        fields = ' and '.join(filter(None, (settings['key_env'], settings['model_env'])))
        raise ValueError(f'Configure {fields} locally.')
    if settings['provider'] == 'gemini':
        from .gemini import GeminiClient

        return GeminiClient()
    if settings['provider'] == 'local':
        from .local import LocalChatClient

        return LocalChatClient()
    from .openai import OpenAIClient

    return OpenAIClient()
