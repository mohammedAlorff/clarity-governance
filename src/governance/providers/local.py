"""Loopback-only OpenAI-compatible Chat Completions adapter for local models."""

import ipaddress
import json
import os
from urllib.parse import urlsplit

import httpx

from ..contracts import FINAL_SCHEMA, ProviderError, ProviderUnavailable


def _local_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != 'http'
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip('/') not in {'', '/v1'}
    ):
        raise ValueError('Local model URL must be an HTTP loopback OpenAI-compatible endpoint.')
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == 'localhost'
    if not loopback:
        raise ValueError('Local model URL must use a loopback address.')
    return value.rstrip('/') + ('/v1' if not parsed.path.rstrip('/') else '')


class LocalChatClient:
    provider = 'local'

    def __init__(self, model=None, base_url=None, *, transport=None):
        self.model = model if model is not None else os.getenv('LOCAL_MODEL', '')
        self.base_url = _local_url(
            base_url
            if base_url is not None
            else os.getenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:1234/v1')
        )
        self._transport = transport
        if not self.model:
            raise ValueError('LOCAL_MODEL must be configured.')

    @staticmethod
    def _messages(messages):
        result = []
        for message in messages:
            kind = message.get('type')
            if kind == 'function_call':
                result.append(
                    {
                        'role': 'assistant',
                        'tool_calls': [
                            {
                                'id': message['call_id'],
                                'type': 'function',
                                'function': {
                                    'name': message['name'],
                                    'arguments': message['arguments'],
                                },
                            }
                        ],
                    }
                )
            elif kind == 'function_call_output':
                result.append(
                    {
                        'role': 'tool',
                        'tool_call_id': message['call_id'],
                        'content': message['output'],
                    }
                )
            else:
                result.append({'role': message['role'], 'content': message['content']})
        contract = (
            '\nWhen returning the final answer, return only JSON matching this schema: '
            + json.dumps(FINAL_SCHEMA, separators=(',', ':'))
        )
        if result and result[0].get('role') == 'system':
            result[0]['content'] += contract
        else:
            result.insert(0, {'role': 'system', 'content': contract.lstrip()})
        return result

    def input_size(self, messages, tools):
        local_tools = [
            {
                'type': 'function',
                'function': {key: tool[key] for key in ('name', 'description', 'parameters')},
            }
            for tool in tools
        ]
        return (
            len(
                json.dumps(
                    {'messages': self._messages(messages), 'tools': local_tools}, ensure_ascii=False
                ).encode('utf-8')
            )
            + 256
        )

    def respond(self, messages, tools, max_tokens, timeout):
        request = {
            'model': self.model,
            'messages': self._messages(messages),
            'tools': [
                {
                    'type': 'function',
                    'function': {key: tool[key] for key in ('name', 'description', 'parameters')},
                }
                for tool in tools
            ],
            'stream': False,
            'max_tokens': max_tokens,
        }
        try:
            with httpx.Client(
                transport=self._transport, timeout=timeout, follow_redirects=False
            ) as client:
                with client.stream(
                    'POST', self.base_url + '/chat/completions', json=request
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 512000:
                            raise ProviderError('Provider response exceeded size limit.')
                    payload = json.loads(body)
            choices = payload.get('choices') if isinstance(payload, dict) else None
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError('Invalid choices.')
            choice = choices[0]
            if choice.get('finish_reason') not in {'stop', 'tool_calls'}:
                raise ProviderError('Provider did not complete the response.')
            message = choice['message']
            calls = []
            for item in message.get('tool_calls') or []:
                function = item['function']
                args = json.loads(function['arguments'])
                if not isinstance(args, dict):
                    raise ValueError('Invalid tool arguments.')
                calls.append({'name': function['name'], 'arguments': args, 'call_id': item['id']})
            proposals = None
            if calls:
                if message.get('content'):
                    raise ValueError('Mixed tool and final response.')
            else:
                content = message.get('content')
                if not isinstance(content, str):
                    raise ValueError('Missing final response.')
                # Qwen reasoning models may include a private-looking think block;
                # only parse the answer after its closing marker.
                if '</think>' in content:
                    content = content.rsplit('</think>', 1)[1]
                content = content.strip()
                if content.startswith('```'):
                    content = content.strip('`').strip()
                    if content.startswith('json'):
                        content = content[4:].strip()
                final = json.loads(content)
                if (
                    not isinstance(final, dict)
                    or set(final) != {'proposals'}
                    or not isinstance(final['proposals'], list)
                ):
                    raise ValueError('Invalid final response.')
                proposals = final['proposals']
            usage = payload.get('usage', {})
            mapped = {}
            if isinstance(usage, dict):
                for source, target in (
                    ('prompt_tokens', 'input_tokens'),
                    ('completion_tokens', 'output_tokens'),
                ):
                    amount = usage.get(source)
                    if type(amount) is int and amount >= 0:
                        mapped[target] = amount
                # OpenAI-compatible local servers differ in whether they expose
                # prompt-cache usage. Preserve explicit evidence only; absence
                # remains unknown and cannot qualify as an uncached trial.
                for key in ('prompt_tokens_details', 'input_tokens_details'):
                    details = usage.get(key)
                    if isinstance(details, dict):
                        cached = details.get('cached_tokens')
                        if type(cached) is int and cached >= 0:
                            mapped['input_tokens_details'] = {'cached_tokens': cached}
                            break
            model = payload.get('model', self.model)
            return {
                'provider': self.provider,
                'calls': calls,
                'proposals': proposals,
                'usage': mapped,
                'model': model,
            }
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise ProviderUnavailable('The local model server is unavailable.') from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError('Provider request failed or returned invalid data.') from None
