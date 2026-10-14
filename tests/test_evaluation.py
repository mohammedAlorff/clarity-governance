import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from governance.evaluation import json_hash, runtime_contract, source_identity
from governance.source import DemoSource

SOURCE_HASH = DemoSource().snapshot_hash()
SCHEMA_HASH = source_identity(DemoSource())['schema_hash']
BASELINE = {
    'rules': [
        {
            'rule_id': 'required',
            'metric_id': 'completeness',
            'target': {'table': 'customers', 'column': 'email'},
            'parameters': {},
        }
    ]
}
BASELINE_HASH = json_hash(BASELINE)
MANIFEST = {
    'reference_reviewed': True,
    'reference_hash': 'ref1',
    'targets_approved': True,
    'targets': {'precision': 0.8, 'recall': 0.8},
    'source_hash': SOURCE_HASH,
    'schema_hash': SCHEMA_HASH,
    'baseline_hash': BASELINE_HASH,
    'split': 'held_out',
    'budgets': {'max_calls': 30, 'max_steps': 8, 'max_tokens': 16000},
    'protocol_version': '1',
    'reviewer': 'advisor',
    'frozen_at': '2026-09-26T00:00:00Z',
    'provider': 'openai',
    'resolved_model': 'configured-model',
    'cache_disabled_attested': True,
    'cache_attestor': 'test-operator',
    'runtime_contract': runtime_contract(),
}


def trial(approach, run_id):
    return {
        'approach': approach,
        'split': 'held_out',
        'run_id': run_id,
        'cached': False,
        'usage': {'cache_usage_known': True, 'cached_tokens': 0},
        'provider': 'openai',
        'model': 'configured-model',
        'source_hash': SOURCE_HASH,
        'source_hash_after': SOURCE_HASH,
        'source_identity': {'source_hash': SOURCE_HASH, 'schema_hash': SCHEMA_HASH},
        'reference_hash': 'ref1',
        'runtime_contract': MANIFEST['runtime_contract'],
        'budgets': MANIFEST['budgets'],
        'started_at': '2026-09-27T00:00:00Z',
        'status': 'completed',
        'metrics': {'precision': 0.8, 'recall': 0.6, 'f1': 24 / 35},
    }


class EvaluationTests(unittest.TestCase):
    def test_detections_deduplicate_rule_row_target_tuples(self):
        from governance.evaluation import detection_metrics

        a = {'rule_id': 'a', 'row_id': 1, 'target': {'table': 't', 'column': 'c'}}
        b = {'rule_id': 'b', 'row_id': 1, 'target': {'table': 't', 'column': 'c'}}
        result = detection_metrics([a, a, b], [a])
        self.assertEqual((result['tp'], result['fp'], result['fn']), (1, 1, 0))
        self.assertEqual(result['precision'], 0.5)
        self.assertEqual(result['recall'], 1)
        self.assertAlmostEqual(result['f1'], 2 / 3)

    def test_undefined_denominators_remain_not_applicable(self):
        from governance.evaluation import detection_metrics

        a = {'rule_id': 'a', 'row_id': '1', 'target': 't.c'}
        self.assertIsNone(detection_metrics([], [a])['precision'])
        self.assertEqual(detection_metrics([], [a])['recall'], 0)
        self.assertIsNone(detection_metrics([], [])['f1'])

    def test_missing_identifiers_are_rejected(self):
        from governance.evaluation import detection_metrics

        with self.assertRaises(ValueError):
            detection_metrics([{'rule_id': 'a'}], [])

    def test_composite_row_keys_ignore_dict_order_but_preserve_types(self):
        from governance.evaluation import detection_metrics

        predicted = {'rule_id': 'r', 'row_id': {'order_id': 1, 'line_id': 2}, 'target': 't.c'}
        reference = {'rule_id': 'r', 'row_id': {'line_id': 2, 'order_id': 1}, 'target': 't.c'}
        self.assertEqual(detection_metrics([predicted], [reference])['tp'], 1)
        reference['row_id']['order_id'] = '1'
        self.assertEqual(detection_metrics([predicted], [reference])['tp'], 0)

    def test_freeze_requires_human_review_and_targets_before_trials(self):
        from governance.evaluation import validate_freeze

        self.assertEqual(validate_freeze(MANIFEST)['status'], 'ready')
        missing = copy.deepcopy(MANIFEST)
        missing['targets_approved'] = False
        self.assertEqual(validate_freeze(missing)['status'], 'pending')

    def test_final_evaluation_requires_three_uncached_trials_each_and_matching_frozen_inputs(self):
        from governance.evaluation import validate_freeze

        trials = [trial(approach, approach + str(i)) for approach in ('B', 'C') for i in range(3)]
        self.assertEqual(validate_freeze(MANIFEST, trials)['status'], 'ready')
        trials[0]['cached'] = True
        self.assertEqual(validate_freeze(MANIFEST, trials)['status'], 'pending')
        trials[0]['cached'] = False
        trials[0]['started_at'] = '2026-09-25T00:00:00Z'
        self.assertEqual(validate_freeze(MANIFEST, trials)['status'], 'pending')

    def test_trial_summary_excludes_synthetic_and_preserves_missing_metrics(self):
        from governance.evaluation import summarize_trials

        trials = [trial('B', '1'), trial('B', '2')]
        trials[1]['metrics']['precision'] = None
        demo = trial('C', '3')
        demo['provider'] = 'synthetic'
        result = summarize_trials(trials + [demo])
        self.assertEqual(result['approaches']['B']['precision']['mean'], 0.8)
        self.assertEqual(result['approaches']['B']['precision']['n'], 1)
        self.assertEqual(result['excluded_trials'], 1)

    def test_static_baseline_executes_explicit_rules_and_preserves_detection_identity(self):
        from governance.evaluation import run_baseline
        from governance.source import DemoSource

        baseline = {
            'rules': [
                {
                    'rule_id': 'missing_email',
                    'metric_id': 'completeness',
                    'target': {'table': 'customers', 'column': 'email'},
                    'parameters': {},
                }
            ]
        }
        output = run_baseline(DemoSource(), baseline)
        self.assertEqual(len(output['detections']), 1)
        self.assertEqual(output['detections'][0]['rule_id'], 'missing_email')
        self.assertEqual(output['detections'][0]['target'], 'customers.email')

    def test_trial_artifact_remains_unscored_until_human_mapping_is_attached(self):
        from governance.evaluation import complete_trial, freeze_manifest, json_hash, run_trial
        from governance.source import DemoSource

        class Client:
            provider = 'test-provider'
            model = 'test-model'

            def respond(self, messages, tools, max_tokens, timeout):
                return {
                    'proposals': [],
                    'usage': {
                        'input_tokens': 1,
                        'output_tokens': 1,
                        'input_tokens_details': {'cached_tokens': 0},
                    },
                }

        manifest = copy.deepcopy(MANIFEST)
        manifest['budgets'] = {'max_calls': 40, 'max_steps': 8, 'max_tokens': 16000}
        manifest['provider'] = Client.provider
        manifest['resolved_model'] = Client.model
        reference = {'detections': []}
        manifest['reference_hash'] = json_hash(reference)
        with TemporaryDirectory() as directory:
            frozen = freeze_manifest(manifest, Path(directory) / 'frozen.json')
            artifact = run_trial(DemoSource(), Client(), 'B', frozen)
        self.assertEqual(artifact['status'], 'awaiting_human_review')
        self.assertNotIn('metrics', artifact)
        reviewed = complete_trial(
            artifact,
            {
                'reviewer': 'analyst',
                'reference_hash': manifest['reference_hash'],
                'detections': [],
            },
            reference,
        )
        self.assertEqual(reviewed['status'], 'reviewed_unmeasured')
        self.assertIsNone(reviewed['metrics']['precision'])
        self.assertEqual(reviewed['original_proposals'], artifact['original_proposals'])
        with self.assertRaises(ValueError):
            complete_trial(
                artifact,
                {
                    'reviewer': 'analyst',
                    'reference_hash': manifest['reference_hash'],
                    'detections': [],
                },
                {'detections': [{'rule_id': 'changed', 'row_id': 1, 'target': 't.c'}]},
            )

    def test_freeze_manifest_is_write_once_and_detects_tampering(self):
        from governance.evaluation import freeze_manifest, validate_freeze

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'frozen.json'
            frozen = freeze_manifest(MANIFEST, path)
            with self.assertRaises(FileExistsError):
                freeze_manifest(MANIFEST, path)
            frozen['targets']['precision'] = 0.99
            self.assertEqual(validate_freeze(frozen)['status'], 'pending')

    def test_final_trial_counts_are_required_for_each_frozen_case(self):
        from governance.evaluation import validate_freeze

        manifest = copy.deepcopy(MANIFEST)
        manifest['cases'] = [
            {
                'case_id': 'case1',
                'source_hash': SOURCE_HASH,
                'schema_hash': SCHEMA_HASH,
                'baseline_hash': BASELINE_HASH,
                'reference_hash': 'ref1',
            },
            {
                'case_id': 'case2',
                'source_hash': 'source2',
                'schema_hash': SCHEMA_HASH,
                'baseline_hash': BASELINE_HASH,
                'reference_hash': 'ref2',
            },
        ]
        runs = []
        for case in manifest['cases']:
            for approach in ('B', 'C'):
                for index in range(3):
                    run = trial(approach, case['case_id'] + approach + str(index))
                    run.update(case)
                    run['source_identity'] = {
                        'source_hash': case['source_hash'],
                        'schema_hash': case['schema_hash'],
                    }
                    run['source_hash_after'] = case['source_hash']
                    runs.append(run)
        self.assertEqual(validate_freeze(manifest, runs)['status'], 'ready')
        self.assertEqual(validate_freeze(manifest, runs[:6])['status'], 'pending')

    def test_signed_manifest_rejects_trials_from_a_different_protocol(self):
        from governance.evaluation import freeze_manifest, validate_freeze

        with TemporaryDirectory() as directory:
            frozen = freeze_manifest(MANIFEST, Path(directory) / 'frozen.json')
            runs = [trial(a, a + str(i)) for a in ('B', 'C') for i in range(3)]
            for run in runs:
                run['started_at'] = '2099-01-01T00:00:00Z'
                run['manifest_hash'] = 'different protocol'
            self.assertEqual(validate_freeze(frozen, runs)['status'], 'pending')

    def test_source_schema_identity_is_verified_before_any_model_request(self):
        from governance.evaluation import freeze_manifest, run_trial
        from governance.source import DemoSource

        class NoRequests:
            provider = 'test'
            model = 'test'

            def respond(self, *args, **kwargs):
                raise AssertionError('Provider must not be reached.')

        manifest = copy.deepcopy(MANIFEST)
        manifest['schema_hash'] = 'changed-schema'
        with TemporaryDirectory() as directory:
            frozen = freeze_manifest(manifest, Path(directory) / 'frozen.json')
            with self.assertRaises(ValueError):
                run_trial(DemoSource(), NoRequests(), 'C', frozen)

    def test_final_summary_separates_original_and_reviewed_detection_scores(self):
        from governance.evaluation import summarize_trials

        run = trial('B', '1')
        run['original_metrics'] = {'precision': 0.5, 'recall': 0.5, 'f1': 0.5}
        run['reviewed_metrics'] = {'precision': 1, 'recall': 1, 'f1': 1}
        output = summarize_trials([run])
        self.assertEqual(output['original']['B']['precision']['mean'], 0.5)
        self.assertEqual(output['reviewed']['B']['precision']['mean'], 1)

    def test_baseline_tool_budget_exhaustion_does_not_claim_complete_execution(self):
        from governance.contracts import RunLimits
        from governance.evaluation import run_baseline
        from governance.source import DemoSource

        baseline = {
            'rules': [
                {
                    'rule_id': 'a',
                    'metric_id': 'completeness',
                    'target': {'table': 'customers', 'column': 'email'},
                    'parameters': {},
                }
            ]
        }
        output = run_baseline(DemoSource(), baseline, RunLimits(max_calls=1))
        self.assertEqual(output['status'], 'budget_exhausted')
        self.assertEqual(output['detections'], [])

    def test_freeze_rejects_unknown_budget_options_and_records_effective_defaults(self):
        from governance.evaluation import freeze_manifest, validate_freeze

        manifest = copy.deepcopy(MANIFEST)
        manifest['budgets']['unbounded_retry'] = True
        self.assertEqual(validate_freeze(manifest)['status'], 'pending')
        with TemporaryDirectory() as directory:
            frozen = freeze_manifest(MANIFEST, Path(directory) / 'frozen.json')
            self.assertIn('max_seconds', frozen['budgets'])
            self.assertIn('max_output_tokens', frozen['budgets'])
            self.assertIn('max_retries', frozen['budgets'])

    def test_offline_cli_freezes_and_scores_but_rejects_incomplete_final_trials(self):
        import contextlib
        import io

        from governance.evaluation import main

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'protocol.json').write_text(json.dumps(MANIFEST), encoding='utf-8')
            (root / 'result.json').write_text(json.dumps({'detections': []}), encoding='utf-8')
            (root / 'trials.json').write_text('[]', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(['freeze', str(root / 'protocol.json'), str(root / 'frozen.json')]), 0
                )
                self.assertEqual(
                    main(['evaluate', str(root / 'result.json'), str(root / 'result.json')]), 0
                )
                self.assertEqual(
                    main(['final', str(root / 'frozen.json'), str(root / 'trials.json')]), 2
                )
