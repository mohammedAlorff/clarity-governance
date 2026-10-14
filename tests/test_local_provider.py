"""The local OpenAI-compatible adapter routes Qwen without a cloud credential."""

import json

import httpx
import pytest

from governance.contracts import FINAL_SCHEMA, ProviderError
from governance.providers.local import LocalChatClient


def test_lm_studio_tool_call_response_and_no_key(monkeypatch):
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'model': 'qwen3-4b-instruct-2507',
                'choices': [
                    {
                        'finish_reason': 'tool_calls',
                        'message': {
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_1',
                                    'type': 'function',
                                    'function': {'name': 'get_schema', 'arguments': '{}'},
                                }
                            ],
                        },
                    }
                ],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 5, 'total_tokens': 17},
            },
        )

    monkeypatch.setenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:1234/v1')
    client = LocalChatClient(model='qwen3-4b-instruct-2507', transport=httpx.MockTransport(handle))
    tool = {
        'type': 'function',
        'name': 'get_schema',
        'description': 'Read schema.',
        'parameters': {
            'type': 'object',
            'properties': {},
            'required': [],
            'additionalProperties': False,
        },
        'strict': True,
    }
    result = client.respond([{'role': 'user', 'content': 'Inspect.'}], [tool], 100, 5)
    assert result['provider'] == 'local'
    assert result['calls'] == [{'name': 'get_schema', 'arguments': {}, 'call_id': 'call_1'}]
    assert result['usage'] == {'input_tokens': 12, 'output_tokens': 5}
    assert requests[0]['tools'][0]['function']['name'] == 'get_schema'
    assert requests[0]['stream'] is False
    assert requests[0]['model'] == 'qwen3-4b-instruct-2507'


def test_local_cache_usage_requires_explicit_provider_metadata():
    def handle(request):
        return httpx.Response(
            200,
            json={
                'model': 'qwen3-4b-instruct-2507',
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{"proposals": []}'}}],
                'usage': {
                    'prompt_tokens': 10,
                    'completion_tokens': 2,
                    'prompt_tokens_details': {'cached_tokens': 0},
                },
            },
        )

    client = LocalChatClient(model='qwen3-4b-instruct-2507', transport=httpx.MockTransport(handle))
    result = client.respond([{'role': 'user', 'content': 'Inspect.'}], [], 100, 5)
    assert result['usage']['input_tokens_details'] == {'cached_tokens': 0}


def test_tool_history_is_mapped_to_chat_completions_format(monkeypatch):
    request = {}

    def handle(http_request):
        request.update(json.loads(http_request.content))
        return httpx.Response(
            200,
            json={
                'model': 'qwen3-4b-instruct-2507',
                'choices': [
                    {
                        'finish_reason': 'stop',
                        'message': {'role': 'assistant', 'content': '{"proposals": []}'},
                    }
                ],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 4},
            },
        )

    monkeypatch.setenv('LOCAL_LLM_BASE_URL', 'http://localhost:1234/v1')
    client = LocalChatClient(model='qwen3-4b-instruct-2507', transport=httpx.MockTransport(handle))
    messages = [
        {'role': 'system', 'content': 'Use the tools.'},
        {'role': 'user', 'content': 'Inspect.'},
        {'type': 'function_call', 'name': 'get_schema', 'arguments': '{}', 'call_id': 'call_1'},
        {'type': 'function_call_output', 'call_id': 'call_1', 'output': '{"tables": []}'},
    ]
    result = client.respond(messages, [], 100, 5)
    assert result['proposals'] == []
    assert request['messages'][2]['tool_calls'][0]['id'] == 'call_1'
    assert request['messages'][3] == {
        'role': 'tool',
        'tool_call_id': 'call_1',
        'content': '{"tables": []}',
    }


def test_local_endpoint_rejects_non_loopback_and_credentials():
    with pytest.raises(ValueError):
        LocalChatClient('qwen', base_url='http://example.com/v1')
    with pytest.raises(ValueError):
        LocalChatClient('qwen', base_url='http://user:pass@127.0.0.1:1234/v1')


def test_provider_factory_selects_local_qwen_without_openai_key(monkeypatch):
    from governance.providers import create_client, model_settings

    monkeypatch.setenv('LLM_PROVIDER', 'local')
    monkeypatch.setenv('LOCAL_MODEL', 'qwen3-4b-instruct-2507')
    monkeypatch.setenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:1234/v1')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    settings = model_settings()
    assert settings['configured'] is True
    client = create_client()
    assert client.provider == 'local'
    assert client.model == 'qwen3-4b-instruct-2507'


def test_schema_is_sent_to_local_model_and_counted_in_budget():
    captured = {}

    def handle(request):
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{"proposals": []}'}}]
            },
        )

    client = LocalChatClient('qwen', transport=httpx.MockTransport(handle))
    messages = [{'role': 'system', 'content': 'Inspect safely.'}]
    original = json.loads(json.dumps(messages))
    client.respond(messages, [], 100, 5)
    assert json.dumps(FINAL_SCHEMA, separators=(',', ':')) in captured['messages'][0]['content']
    assert client.input_size(messages, []) >= len(json.dumps(captured).encode())
    assert messages == original


@pytest.mark.parametrize('finish_reason', ['length', 'content_filter', None])
def test_unfinished_output_is_not_accepted_even_with_parseable_json(finish_reason):
    client = LocalChatClient(
        'qwen',
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    'choices': [
                        {
                            'finish_reason': finish_reason,
                            'message': {'content': '{"proposals": []}'},
                        }
                    ]
                },
            )
        ),
    )
    with pytest.raises(ProviderError):
        client.respond([], [], 100, 5)


def test_switched_off_local_server_stops_without_retries_or_synthetic_fallback():
    from governance.agent import run_inspection
    from governance.source import DemoSource

    requests = []

    def disconnected(request):
        requests.append(request)
        raise httpx.ConnectError('PRIVATE diagnostic', request=request)

    client = LocalChatClient('qwen', transport=httpx.MockTransport(disconnected))
    result = run_inspection(DemoSource(), client=client, mode='agent')
    assert result['status'] == 'provider_unavailable'
    assert len(requests) == 1
    assert result['provider'] == 'local'
    assert result['proposals'] == []
    assert 'PRIVATE' not in json.dumps(result)


def test_preflight_rejects_remote_local_endpoint_without_request(monkeypatch):
    from governance.readiness import inspection_readiness
    from governance.source import DemoSource

    monkeypatch.setenv('LLM_PROVIDER', 'local')
    monkeypatch.setenv('LOCAL_MODEL', 'qwen')
    monkeypatch.setenv('LOCAL_LLM_BASE_URL', 'https://example.com/v1')
    check = inspection_readiness(DemoSource().get_schema(), 'demo', 'agent')
    assert not check['ready']
    assert check['issues'][0]['code'] == 'provider_configuration'


def test_local_root_url_is_normalized_to_v1():
    assert (
        LocalChatClient('qwen', base_url='http://127.0.0.1:1234').base_url
        == 'http://127.0.0.1:1234/v1'
    )
