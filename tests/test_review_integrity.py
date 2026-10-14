import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from governance.store import Conflict, Store


class ReviewIntegrityTests(unittest.TestCase):
    def test_edit_of_approved_rule_requires_new_approval(self):
        with TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'state.db')
            scope = store.new_scope('demo', 'test')
            original = {
                'kind': 'rule',
                'target': {'table': 't', 'column': 'c'},
                'title': 'Required',
                'description': 'Present',
                'evidence': ['reference'],
                'assumptions': [],
                'rule': {
                    'metric_id': 'completeness',
                    'target': {'table': 't', 'column': 'c'},
                    'parameters': {},
                },
            }
            p = store.add_proposal(scope, original)
            store.review(p['id'], 'approve', 'Ada', review_seconds=3.25)
            self.assertEqual(len(store.approved_rules(scope)), 1)
            edited = store.review(p['id'], 'edit', 'Ada', changes={'title': 'Updated'})
            self.assertEqual(store.approved_rules(scope), [])
            self.assertEqual(edited['original']['title'], 'Required')
            self.assertEqual(edited['history'][0]['reviews'][0]['review_seconds'], 3.25)
            self.assertEqual(edited['status'], 'draft')
            self.assertEqual(store.get_proposal(p['id'])['status'], 'approved')

    def test_two_reviewers_cannot_decide_same_version_twice(self):
        with TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'state.db')
            scope = store.new_scope('demo', 'test')
            p = store.add_proposal(scope, {'kind': 'description', 'title': 'A', 'description': 'B'})

            def decide(action):
                try:
                    store.review(p['id'], action, action)
                    return 'ok'
                except Conflict:
                    return 'conflict'

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(decide, ['approve', 'reject']))
            self.assertCountEqual(results, ['ok', 'conflict'])


if __name__ == '__main__':
    unittest.main()
