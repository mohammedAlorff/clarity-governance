"""Gemini Interactions adapter. Secrets and opaque signatures stay out of reports."""

import json
import os

import httpx

from ..contracts import FINAL_SCHEMA, ProviderError


class GeminiClient:
    provider = 'gemini'

    def __init__(self, api_key=None, model=None, *, transport=None):
        self._api_key = api_key if api_key is not None else os.getenv('GEMINI_API_KEY', '')
        self.model = model if model is not None else os.getenv('GEMINI_MODEL', '')
        if not self._api_key or not self.model:
            raise ValueError('GEMINI_API_KEY and GEMINI_MODEL must both be configured.')
        self._transport = transport
        self._messages = None
        self._calls = {}
        self._batch = 0

    def _request(self, messages, tools, max_tokens):
        # The inspection loop owns one message list per run. Holding its identity
        # avoids carrying provider state into another run, even for the same source.
        if self._messages is not messages:
            self._messages, self._calls, self._batch = messages, {}, 0
        steps, systems, calls, results = [], [], [], []
        batch = None

        def flush():
            steps.extend(calls)
            steps.extend(results)
            calls.clear()
            results.clear()

        names = {}
        for message in messages:
            kind = message.get('type')
            if kind == 'function_call':
                local_id = message['call_id']
                metadata = self._calls[local_id]
                if batch != metadata['batch']:
                    flush()
                    batch = metadata['batch']
                calls.extend(metadata['thoughts'])
                calls.append(
                    {
                        'type': 'function_call',
                        'id': metadata['id'],
                        'name': message['name'],
                        'arguments': json.loads(message['arguments']),
                    }
                )
                names[local_id] = message['name']
            elif kind == 'function_call_output':
                local_id = message['call_id']
                results.append(
                    {
                        'type': 'function_result',
                        'call_id': self._calls[local_id]['id'],
                        'name': names[local_id],
                        'result': [{'type': 'text', 'text': message['output']}],
                    }
                )
            else:
                flush()
                if message['role'] == 'system':
                    systems.append(message['content'])
                else:
                    steps.append(
                        {
                            'type': 'user_input',
                            'content': [{'type': 'text', 'text': message['content']}],
                        }
                    )
        flush()
        return {
            'model': self.model,
            'input': steps,
            'system_instruction': '\n'.join(systems),
            'tools': [
                {key: tool[key] for key in ('type', 'name', 'description', 'parameters')}
                for tool in tools
            ],
            'store': False,
            'generation_config': {'max_output_tokens': max_tokens, 'thinking_summaries': 'none'},
            'response_format': {
                'type': 'text',
                'mime_type': 'application/json',
                'schema': FINAL_SCHEMA,
            },
        }

    def input_size(self, messages, tools):
        """Conservative UTF-8 input bound, including private thought signatures."""
        request = self._request(messages, tools, 1)
        return len(json.dumps(request).encode('utf-8')) + 128 * len(request['input'])

    def respond(self, messages, tools, max_tokens, timeout):
        try:
            request = self._request(messages, tools, max_tokens)
            with httpx.Client(
                transport=self._transport, timeout=timeout, follow_redirects=False
            ) as client:
                with client.stream(
                    'POST',
                    'https://generativelanguage.googleapis.com/v1beta/interactions',
                    json=request,
                    headers={'x-goog-api-key': self._api_key},
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 512000:
                            raise ProviderError('Provider response exceeded size limit.')
                    payload = json.loads(body)
            if (
                not isinstance(payload, dict)
                or payload.get('status') not in {'completed', 'requires_action'}
                or payload.get('errors')
            ):
                raise ProviderError('Provider did not complete the response.')
            steps = payload.get('steps')
            if not isinstance(steps, list) or len(steps) > 100:
                raise ValueError('Invalid steps.')
            calls, texts, thoughts, metadata, native_ids = [], [], [], {}, set()
            for step in steps:
                kind = step['type']
                if kind == 'thought':
                    signature = step.get('signature')
                    if signature is not None:
                        if not isinstance(signature, str):
                            raise ValueError('Invalid signature.')
                        thoughts.append({'type': 'thought', 'signature': signature})
                elif kind == 'function_call':
                    if not isinstance(step['arguments'], dict) or not isinstance(step['name'], str):
                        raise ValueError('Invalid function call.')
                    native_id = step['id']
                    if (
                        not isinstance(native_id, str)
                        or not 1 <= len(native_id) <= 500
                        or native_id in native_ids
                    ):
                        raise ValueError('Invalid call ID.')
                    native_ids.add(native_id)
                    local_id = f'gemini_call_{len(self._calls) + len(calls) + 1}'
                    metadata[local_id] = {
                        'id': native_id,
                        'thoughts': thoughts,
                        'batch': self._batch,
                    }
                    thoughts = []
                    calls.append(
                        {'name': step['name'], 'arguments': step['arguments'], 'call_id': local_id}
                    )
                elif kind == 'model_output':
                    if step.get('error'):
                        raise ValueError('Provider output error.')
                    for content in step.get('content', []):
                        if content['type'] != 'text' or not isinstance(content['text'], str):
                            raise ValueError('Unexpected response content.')
                        texts.append(content['text'])
                else:
                    raise ValueError('Unexpected provider step.')
            proposals = None
            if calls and texts or not calls and payload['status'] != 'completed':
                raise ValueError('Mixed or unfinished response.')
            if not calls:
                final = json.loads(''.join(texts))
                if (
                    not isinstance(final, dict)
                    or set(final) != {'proposals'}
                    or not isinstance(final['proposals'], list)
                ):
                    raise ValueError('Invalid structured final.')
                proposals = final['proposals']
            usage = self._usage(payload.get('usage', {}))
            # Commit private metadata only after parsing succeeds; retries are idempotent.
            self._calls.update(metadata)
            self._batch += 1
            return {
                'calls': calls,
                'proposals': proposals,
                'usage': usage,
                'model': payload.get('model', self.model),
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError('Provider request failed or returned invalid data.') from None

    @staticmethod
    def _usage(stats):
        if not isinstance(stats, dict):
            raise ValueError('Invalid usage.')
        for key in (
            'total_input_tokens',
            'total_output_tokens',
            'total_thought_tokens',
            'total_cached_tokens',
            'total_tokens',
        ):
            if key in stats and (type(stats[key]) is not int or stats[key] < 0):
                raise ValueError('Invalid token count.')
        usage = {}
        if 'total_input_tokens' in stats:
            usage['input_tokens'] = stats['total_input_tokens']
        if 'total_output_tokens' in stats and 'total_thought_tokens' in stats:
            usage['output_tokens'] = stats['total_output_tokens'] + stats['total_thought_tokens']
        if 'total_cached_tokens' in stats:
            usage['input_tokens_details'] = {'cached_tokens': stats['total_cached_tokens']}
        return usage
