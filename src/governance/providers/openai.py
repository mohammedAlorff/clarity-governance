"""OpenAI Responses adapter; transport details stay outside the inspection loop."""

import json
import os

from ..contracts import FINAL_SCHEMA, ProviderError


class OpenAIClient:
    provider = 'openai'

    def __init__(self, api_key=None, model=None, *, transport=None):
        self._api_key = api_key if api_key is not None else os.environ.get('OPENAI_API_KEY', '')
        self.model = model if model is not None else os.environ.get('OPENAI_MODEL', '')
        self._transport = transport
        if not self._api_key or not self.model:
            raise ValueError('OPENAI_API_KEY and OPENAI_MODEL must both be configured.')

    def respond(self, messages, tools, max_tokens, timeout):
        """Responses API with strict tool schemas and validated structured finals.

        No request is made during construction. The caller owns bounded retries.
        HTTP response bodies and exception strings never enter traces or errors.
        """
        import httpx

        request = {
            'model': self.model,
            'input': messages,
            'tools': tools,
            'store': False,
            'max_output_tokens': max_tokens,
            'parallel_tool_calls': False,
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': 'governance_proposals',
                    'strict': True,
                    'schema': FINAL_SCHEMA,
                }
            },
        }
        try:
            with httpx.Client(
                transport=self._transport, timeout=timeout, follow_redirects=False
            ) as client:
                response = client.post(
                    'https://api.openai.com/v1/responses',
                    json=request,
                    headers={'Authorization': 'Bearer ' + self._api_key},
                )
                response.raise_for_status()
                if len(response.content) > 512000:
                    raise ProviderError('Provider response exceeded size limit.')
                payload = response.json()
            if not isinstance(payload, dict) or payload.get('status') in {
                'failed',
                'incomplete',
                'cancelled',
            }:
                raise ProviderError('Provider did not complete the response.')
            calls, proposals = [], None
            for item in payload.get('output', [])[:100]:
                if item.get('type') == 'function_call':
                    arguments = json.loads(item['arguments'])
                    calls.append(
                        {'name': item['name'], 'arguments': arguments, 'call_id': item['call_id']}
                    )
                elif item.get('type') == 'message':
                    for content in item.get('content', []):
                        if content.get('type') == 'refusal':
                            raise ProviderError('Provider refused inspection.')
                        if content.get('type') == 'output_text':
                            final = json.loads(content['text'])
                            if not isinstance(final, dict) or set(final) != {'proposals'}:
                                raise ProviderError('Invalid structured response.')
                            proposals = final['proposals']
            return {
                'calls': calls,
                'proposals': proposals,
                'usage': payload.get('usage', {}),
                'model': payload.get('model', self.model),
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError('Provider request failed or returned invalid data.') from None
