import json

import httpx
import pytest

from governance.agent import run_inspection
from governance.contracts import ProviderError
from tests.test_agent import Source, proposal


def response(steps, **usage):
    return {'status': 'completed', 'model': 'gemini-test', 'steps': steps, 'usage': usage}


def final():
    return {
        'type': 'model_output',
        'content': [{'type': 'text', 'text': json.dumps({'proposals': [proposal()]})}],
    }


def test_gemini_round_trip_preserves_signature_and_filters_source_data():
    from governance.providers.gemini import GeminiClient

    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url == 'https://generativelanguage.googleapis.com/v1beta/interactions'
        assert request.headers['x-goog-api-key'] == 'TEST_SECRET'
        assert 'TEST_SECRET' not in request.url.query.decode()
        assert body['store'] is False
        assert body['response_format']['mime_type'] == 'application/json'
        assert body['generation_config']['max_output_tokens'] <= 3000
        assert all('strict' not in tool for tool in body['tools'])
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=response(
                    [
                        {
                            'type': 'thought',
                            'signature': 'OPAQUE_SIGNATURE',
                            'summary': [{'type': 'text', 'text': 'PRIVATE_THOUGHT'}],
                        },
                        {
                            'type': 'function_call',
                            'id': 'provider.id/1',
                            'name': 'run_metric',
                            'arguments': {
                                'metric_id': 'profile',
                                'target': {'table': 'customers', 'column': 'email'},
                                'parameters': {},
                            },
                        },
                    ],
                    total_input_tokens=100,
                    total_output_tokens=20,
                    total_thought_tokens=10,
                    total_cached_tokens=0,
                ),
            )
        return httpx.Response(
            200,
            json=response(
                [final()],
                total_input_tokens=200,
                total_output_tokens=30,
                total_thought_tokens=5,
                total_cached_tokens=0,
            ),
        )

    client = GeminiClient(
        api_key='TEST_SECRET', model='gemini-test', transport=httpx.MockTransport(handle)
    )
    result = run_inspection(Source(), client, 'agent')
    assert result['status'] == 'completed'
    assert result['provider'] == 'gemini'
    assert result['usage']['input_tokens'] == 300
    assert result['usage']['output_tokens'] == 65  # Includes billed thinking.
    assert result['usage']['cache_usage_known'] is True
    steps = requests[1]['input']
    assert steps[-3] == {'type': 'thought', 'signature': 'OPAQUE_SIGNATURE'}
    assert steps[-2]['id'] == steps[-1]['call_id'] == 'provider.id/1'
    assert steps[-1]['type'] == 'function_result'
    assert 'null_count' in json.dumps(steps[-1])
    assert 'CANARY' not in json.dumps(requests)
    assert 'PRIVATE_THOUGHT' not in json.dumps(requests)
    assert 'OPAQUE_SIGNATURE' not in json.dumps(result)


def test_retry_does_not_duplicate_history_and_new_run_clears_private_state():
    from governance.providers.gemini import GeminiClient

    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(503, text='SECRET_PROVIDER_ERROR')
        return httpx.Response(200, json=response([final()]))

    client = GeminiClient(api_key='TEST', model='test', transport=httpx.MockTransport(handle))
    result = run_inspection(Source(), client, 'agent')
    assert result['status'] == 'completed'
    assert requests[0] == requests[1]
    assert result['usage']['usage_known'] is False
    assert result['usage']['cache_usage_known'] is False
    assert run_inspection(Source(), client, 'agent')['status'] == 'completed'
    assert requests[2]['input'] == requests[0]['input']


@pytest.mark.parametrize(
    'payload',
    [
        {'status': 'incomplete', 'steps': [final()]},
        response(
            [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'not json SECRET'}]}]
        ),
        response([{'type': 'google_search_call', 'id': 'x'}]),
        response(
            [
                {
                    'type': 'function_call',
                    'name': 'get_schema',
                    'id': 'x',
                    'arguments': 'not an object',
                }
            ]
        ),
        response([final()], total_input_tokens=-1),
    ],
)
def test_malformed_and_incomplete_responses_are_safe(payload):
    from governance.providers.gemini import GeminiClient

    client = GeminiClient(
        api_key='TEST',
        model='test',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    with pytest.raises(ProviderError) as caught:
        client.respond([{'role': 'user', 'content': 'inspect'}], [], 100, 2)
    assert 'SECRET' not in str(caught.value)


def test_signature_is_budgeted_and_not_carried_into_next_run():
    from governance.providers.gemini import GeminiClient

    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=response(
                    [
                        {'type': 'thought', 'signature': 'x' * 30000},
                        {
                            'type': 'function_call',
                            'id': 'call',
                            'name': 'get_schema',
                            'arguments': {},
                        },
                    ]
                ),
            )
        return httpx.Response(200, json=response([final()]))

    client = GeminiClient(api_key='TEST', model='test', transport=httpx.MockTransport(handle))
    assert run_inspection(Source(), client, 'agent')['status'] == 'budget_exhausted'
    assert len(requests) == 1
    assert run_inspection(Source(), client, 'agent')['status'] == 'completed'
    assert 'signature' not in json.dumps(requests[-1])


def test_fixed_workflow_sends_profiles_without_tools_and_missing_usage_stays_unknown():
    from governance.providers.gemini import GeminiClient

    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json=response([final()], total_input_tokens=10, total_output_tokens=3)
        )

    client = GeminiClient(api_key='TEST', model='test', transport=httpx.MockTransport(handle))
    result = run_inspection(Source(), client, 'fixed')
    assert result['status'] == 'completed'
    assert requests[0]['tools'] == []
    assert 'profiles' in json.dumps(requests[0]['input'])
    assert 'CANARY' not in json.dumps(requests)
    assert result['usage']['usage_known'] is False  # Thought count missing.
    assert result['usage']['cache_usage_known'] is False
