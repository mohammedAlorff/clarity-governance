import copy
import json
import os
import unittest
from unittest.mock import patch

SCHEMA = {
    'name': 'fixture',
    'tables': [
        {
            'name': 'customers',
            'row_count': 8,
            'columns': [
                {'name': 'email', 'data_type': 'varchar', 'nullable': True, 'key': None},
                {'name': 'status', 'data_type': 'varchar', 'nullable': False, 'key': None},
            ],
        }
    ],
    'relationships': [],
}


class Source:
    def __init__(self):
        self.calls = []

    def get_schema(self):
        self.calls.append('schema')
        return copy.deepcopy(SCHEMA)

    def run_metric(self, metric_id, target, parameters):
        self.calls.append(metric_id)
        return {
            'metric_id': metric_id,
            'target': target,
            'status': 'completed',
            'row_count': 8,
            'non_null_count': 7,
            'null_count': 1,
            'distinct_count': 6,
            'samples': ['CANARY'],
            'comment': 'CANARY',
            'error': 'CANARY',
        }

    def sample_column(self, table, column, limit):
        self.calls.append('sample')
        return {'table': table, 'column': column, 'samples': ['CANARY'], 'sample_count': 1}


def proposal(target=None):
    return {
        'kind': 'description',
        'target': target or {'table': 'customers', 'column': 'email'},
        'title': 'Email',
        'description': 'Observed text column.',
        'evidence': ['Schema type varchar.'],
        'assumptions': [],
        'status': 'draft',
        'rule': None,
    }


class SequenceClient:
    model = 'offline-test'
    provider = 'offline-test'

    def __init__(self, replies):
        self.replies = iter(replies)
        self.messages = []

    def respond(self, messages, tools, max_tokens, timeout):
        self.messages.append(copy.deepcopy(messages))
        return next(self.replies)


class AgentTests(unittest.TestCase):
    def test_missing_provider_is_visible_and_never_falls_back_to_demo(self):
        from governance.agent import run_inspection

        with patch.dict(os.environ, {}, clear=True):
            result = run_inspection(Source(), mode='agent')
        self.assertEqual(result['status'], 'provider_unavailable')
        self.assertEqual(result['proposals'], [])

    def test_adaptive_loop_filters_every_tool_result(self):
        from governance.agent import run_inspection

        client = SequenceClient(
            [
                {
                    'calls': [
                        {
                            'name': 'run_metric',
                            'arguments': {
                                'metric_id': 'profile',
                                'target': {'table': 'customers', 'column': 'email'},
                                'parameters': {},
                            },
                        }
                    ],
                    'usage': {},
                },
                {
                    'calls': [],
                    'proposals': [proposal()],
                    'usage': {'input_tokens': 3, 'output_tokens': 4},
                },
            ]
        )
        result = run_inspection(Source(), client, 'agent')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['usage']['total_tokens'], 7)
        self.assertNotIn('CANARY', json.dumps(client.messages))
        self.assertNotIn('CANARY', json.dumps(result['trace']))

    def test_unknown_calls_are_blocked_without_source_execution(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits

        source = Source()
        client = SequenceClient(
            [{'calls': [{'name': 'execute_sql', 'arguments': {'sql': 'CANARY'}}]}] * 8
        )
        result = run_inspection(source, client, 'agent', RunLimits(max_calls=2, max_steps=8))
        self.assertEqual(source.calls, ['schema'])
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertLessEqual(len(result['trace']), 2)
        self.assertNotIn('CANARY', json.dumps(result['trace']))

    def test_invalid_proposals_and_call_arguments_do_not_escape_validation(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits

        source = Source()
        client = SequenceClient(
            [{'calls': [], 'proposals': [proposal({'table': 'missing', 'column': 'x'})]}]
        )
        result = run_inspection(source, client, 'agent', RunLimits(max_retries=0))
        self.assertEqual(result['status'], 'invalid_response')
        self.assertEqual(result['proposals'], [])

    def test_tool_failures_and_provider_failures_hide_error_text(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits

        class FailingClient:
            provider = 'test'
            model = 'test'

            def respond(self, *args, **kwargs):
                raise RuntimeError('CANARY credential')

        result = run_inspection(Source(), FailingClient(), 'agent', RunLimits(max_retries=1))
        self.assertEqual(result['status'], 'provider_error')
        self.assertNotIn('CANARY', json.dumps(result))

    def test_total_token_usage_stops_followup_request(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits

        client = SequenceClient(
            [
                {
                    'calls': [{'name': 'get_schema', 'arguments': {}}],
                    'usage': {'input_tokens': 25000, 'output_tokens': 500},
                }
            ]
        )
        result = run_inspection(Source(), client, 'agent', RunLimits(max_tokens=20000))
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(len(client.messages), 1)

    def test_tiny_token_budget_blocks_request_before_provider(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits

        client = SequenceClient([])
        result = run_inspection(Source(), client, 'agent', RunLimits(max_tokens=20))
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(client.messages, [])

    def test_profile_cannot_be_submitted_as_executable_quality_rule(self):
        from governance.agent import run_inspection
        from governance.contracts import RunLimits

        item = proposal()
        item['kind'] = 'rule'
        item['rule'] = {'metric_id': 'profile', 'target': item['target'], 'parameters': {}}
        client = SequenceClient([{'proposals': [item], 'usage': {}}])
        result = run_inspection(Source(), client, 'agent', RunLimits(max_retries=0))
        self.assertEqual(result['status'], 'invalid_response')

    def test_fixed_workflow_collects_predetermined_profiles_before_model(self):
        from governance.agent import run_inspection

        source = Source()
        client = SequenceClient([{'calls': [], 'proposals': [proposal()], 'usage': {}}])
        result = run_inspection(source, client, 'fixed')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(source.calls, ['schema', 'profile', 'profile'])
        self.assertNotIn('CANARY', json.dumps(client.messages))

    def test_demo_proposals_use_evidence_and_include_semantic_clarification(self):
        from governance.agent import run_inspection

        result = run_inspection(Source())
        self.assertEqual(result['provider'], 'synthetic')
        self.assertTrue(any(p['status'] == 'needs_clarification' for p in result['proposals']))
        completeness = next(
            p for p in result['proposals'] if p['rule'] and p['rule']['metric_id'] == 'completeness'
        )
        self.assertTrue(any('1' in x for x in completeness['evidence']))
        self.assertEqual(result['usage']['total_tokens'], 0)

    def test_openai_adapter_parses_tool_calls_and_structured_final_using_local_transport(self):
        import httpx

        from governance.providers.openai import OpenAIClient

        requests = []

        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    'model': 'test-resolved',
                    'usage': {'input_tokens': 2, 'output_tokens': 3},
                    'output': [
                        {
                            'type': 'function_call',
                            'name': 'get_schema',
                            'arguments': '{}',
                            'call_id': 'call_1',
                        }
                    ],
                },
            )

        client = OpenAIClient(
            api_key='local-test-key', model='test', transport=httpx.MockTransport(handle)
        )
        output = client.respond([{'role': 'user', 'content': 'inspect'}], [], 200, 2)
        self.assertEqual(output['calls'][0]['name'], 'get_schema')
        self.assertEqual(output['calls'][0]['call_id'], 'call_1')
        self.assertEqual(output['model'], 'test-resolved')
        self.assertFalse(requests[0]['store'])
        self.assertTrue(requests[0]['text']['format']['strict'])

    def test_cost_is_unknown_until_both_unit_prices_are_explicitly_configured(self):
        from governance.agent import run_inspection

        reply = {'proposals': [], 'usage': {'input_tokens': 100, 'output_tokens': 50}}
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(
                run_inspection(Source(), SequenceClient([reply]), 'agent')['usage']['cost_usd']
            )
        with patch.dict(
            os.environ,
            {'OPENAI_INPUT_PRICE_PER_MILLION': '2', 'OPENAI_OUTPUT_PRICE_PER_MILLION': '10'},
            clear=True,
        ):
            client = SequenceClient([reply])
            client.provider = 'openai'
            usage = run_inspection(Source(), client, 'agent')['usage']
            self.assertAlmostEqual(usage['cost_usd'], 0.0007)
