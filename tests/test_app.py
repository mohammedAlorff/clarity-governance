import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class AppTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from governance.app import create_app

        self.temp = TemporaryDirectory()
        self.app = create_app(Path(self.temp.name) / 'app.db')
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def post(self, path, data):
        response = self.client.post(path, json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_complete_flow_and_rejected_rule_not_executed(self):
        self.post('/api/connect', {'mode': 'demo'})
        state = self.post('/api/inspect', {'mode': 'demo'})
        rules = [p for p in state['proposals'] if p['kind'] == 'rule' and p['status'] == 'draft']
        self.assertGreaterEqual(len(rules), 4)
        for action, p in [('approve', rules[0]), ('reject', rules[1])]:
            self.post(
                '/api/proposals/' + p['id'] + '/review',
                {'action': action, 'reviewer': 'test', 'note': ''},
            )
        self.assertIsNone(self.client.get('/api/state').json()['report'])
        result = self.post('/api/checks/run', {})['report']
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['proposal_id'], rules[0]['id'])
        self.assertEqual(self.client.get('/api/export/report').status_code, 200)
        self.assertIn('text/csv', self.client.get('/api/export/dictionary').headers['content-type'])

    def test_source_switch_invalidates_active_proposals(self):
        self.post('/api/connect', {'mode': 'demo'})
        state = self.post('/api/inspect', {'mode': 'demo'})
        old = state['proposals'][0]['id']
        self.post('/api/connect', {'mode': 'demo'})
        response = self.client.post(
            '/api/proposals/' + old + '/review', json={'action': 'approve', 'reviewer': 'test'}
        )
        self.assertEqual(response.status_code, 409)

    def test_profile_coverage_is_union_across_inspections(self):
        self.post('/api/connect', {'mode': 'demo'})
        runtime = self.app.state.runtime
        store = self.app.state.store
        p = store.add_proposal(
            runtime['scope'],
            {
                'kind': 'rule',
                'target': {'table': 'customers', 'column': 'email'},
                'title': 'Email presence',
                'description': 'Required by test owner',
                'evidence': ['test reference'],
                'assumptions': [],
                'rule': {
                    'metric_id': 'completeness',
                    'target': {'table': 'customers', 'column': 'email'},
                    'parameters': {},
                },
            },
        )
        store.review(p['id'], 'approve', 'test')
        for target in ['customers.email', 'customers.age']:
            store.add_record(
                runtime['scope'],
                'inspection',
                {'profiled_columns': 1, 'inspected_targets': [target]},
            )
        report = self.post('/api/checks/run', {})['report']
        self.assertEqual(report['profiled_columns'], 2)

    def test_report_identifies_changed_approval_scope(self):
        self.post('/api/connect', {'mode': 'demo'})
        state = self.post('/api/inspect', {'mode': 'demo'})
        p = next(p for p in state['proposals'] if p['kind'] == 'rule')
        self.post(
            '/api/proposals/' + p['id'] + '/review', {'action': 'approve', 'reviewer': 'test'}
        )
        state = self.post('/api/checks/run', {})
        self.assertFalse(state['report']['outdated'])
        state = self.post(
            '/api/proposals/' + p['id'] + '/review',
            {'action': 'edit', 'reviewer': 'test', 'changes': {'title': 'Updated expectation'}},
        )
        self.assertTrue(state['report']['outdated'])

    def test_foreign_origin_write_blocked(self):
        response = self.client.post(
            '/api/connect', json={'mode': 'demo'}, headers={'Origin': 'https://evil.example'}
        )
        self.assertEqual(response.status_code, 403)

    def test_edit_validation_and_missing_provider(self):
        self.post('/api/connect', {'mode': 'demo'})
        state = self.post('/api/inspect', {'mode': 'demo'})
        p = next(p for p in state['proposals'] if p['kind'] == 'rule')
        response = self.client.post(
            '/api/proposals/' + p['id'] + '/review',
            json={
                'action': 'edit',
                'reviewer': 'test',
                'changes': {'rule': {'metric_id': 'sql', 'target': p['target'], 'parameters': {}}},
            },
        )
        self.assertEqual(response.status_code, 422)
        with patch.dict(
            os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': '', 'OPENAI_MODEL': ''}
        ):
            response = self.client.post('/api/inspect', json={'mode': 'agent'})
        self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
