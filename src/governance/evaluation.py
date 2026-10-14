"""Local evaluation commands with separate development and frozen trial artifacts."""

import argparse
import hashlib
import json
import math
import statistics
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


def _detection_key(item):
    if not isinstance(item, dict) or any(
        item.get(k) is None for k in ('rule_id', 'row_id', 'target')
    ):
        raise ValueError('Each detection requires rule_id, row_id and target.')
    target = item['target']
    if (
        isinstance(target, dict)
        and isinstance(target.get('table'), str)
        and isinstance(target.get('column'), str)
    ):
        target = target['table'] + '.' + target['column']
    if (
        not isinstance(target, str)
        or not target
        or not str(item['rule_id'])
        or not str(item['row_id'])
    ):
        raise ValueError('Detection identifiers must be nonempty.')
    try:
        row_key = json.dumps(item['row_id'], sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError):
        raise ValueError('Row identifiers must be finite JSON values.') from None
    return str(item['rule_id']), row_key, target


def detection_metrics(predicted, reference):
    """Deduplicate rule/row/target detections before precision, recall and F1."""
    predicted_keys = {_detection_key(item) for item in predicted}
    reference_keys = {_detection_key(item) for item in reference}
    tp = len(predicted_keys & reference_keys)
    fp = len(predicted_keys - reference_keys)
    fn = len(reference_keys - predicted_keys)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        None
        if precision is None or recall is None
        else 2 * tp / (2 * tp + fp + fn)
        if 2 * tp + fp + fn
        else None
    )
    return {
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'predicted_count': len(predicted_keys),
        'reference_count': len(reference_keys),
    }


def _timestamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp if stamp.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def _digest(value):
    content = {key: item for key, item in value.items() if key != 'manifest_hash'}
    return json_hash(content)


def json_hash(value):
    """SHA-256 of sorted compact UTF-8 JSON; whitespace and key order are immaterial."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()


def runtime_contract():
    """Nonsecret implementation and privacy settings bound to a frozen trial."""
    from .sampling import SamplingPolicy

    package = Path(__file__).parent
    files = (
        'agent.py',
        'contracts.py',
        'evaluation.py',
        'evaluation_review.py',
        'privacy.py',
        'privacy_contract.py',
        'sampling.py',
        'quality.py',
        'source.py',
        'snapshot.py',
        'providers/local.py',
        'providers/__init__.py',
        'providers/openai.py',
        'providers/gemini.py',
    )
    return {
        'version': 1,
        'code_sha256': {
            name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in files
        },
        'sampling': asdict(SamplingPolicy.from_env()),
    }


def _cases(manifest):
    cases = manifest.get('cases')
    if cases is None:
        return {
            'default': {
                key: manifest.get(key)
                for key in (
                    'source_hash',
                    'reference_hash',
                    'schema_hash',
                    'baseline_hash',
                    'snapshot_id',
                )
            }
        }
    if not isinstance(cases, list) or not 1 <= len(cases) <= 50:
        raise ValueError('Freeze one to fifty named cases.')
    output = {}
    for case in cases:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get('case_id'), str)
            or not case['case_id']
            or case['case_id'] in output
        ):
            raise ValueError('Case IDs must be unique nonempty strings.')
        if not case.get('source_hash') or not case.get('reference_hash'):
            raise ValueError('Each case requires source and reference hashes.')
        output[case['case_id']] = case
    return output


def source_identity(source):
    """Hash complete selected schema metadata and local, read-only row content."""
    schema = source.current_schema() if hasattr(source, 'current_schema') else source.get_schema()
    return {
        'schema_hash': json_hash(schema),
        'source_hash': source.snapshot_hash(),
    }


def begin_evaluation_snapshot(source):
    """Keep MySQL metadata, row hashes, and checks on one read-only view."""
    if hasattr(source, 'begin_evaluation_snapshot'):
        source.begin_evaluation_snapshot()


def _trial_measurement_valid(run):
    """Check that reported original rows can be traced to measured proposals."""
    review = run.get('human_review')
    if not isinstance(review, dict) or not isinstance(run.get('original_proposals'), list):
        return False
    if (
        review.get('artifact_run_id') != run.get('run_id')
        or review.get('reference_hash') != run.get('reference_hash')
        or review.get('original_proposals_hash') != json_hash(run['original_proposals'])
        or not isinstance(review.get('proposal_assessments'), list)
    ):
        return False
    try:
        derived = _measured_original_detections(run, review)
        reported = run.get('measured_original_detections')
        if derived is None or not isinstance(reported, list):
            return False
        predicted = {_detection_key(item) for item in derived}
        if predicted != {_detection_key(item) for item in reported}:
            return False
        metrics = run.get('original_metrics', {})
        return (
            isinstance(metrics, dict)
            and metrics.get('predicted_count') == len(predicted)
            and metrics.get('tp', -1) + metrics.get('fp', -1) == len(predicted)
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def validate_freeze(manifest, trials=None):
    """Return readiness and reasons. Nothing is marked final while prerequisites lack."""
    reasons = []
    if not isinstance(manifest, dict):
        return {'status': 'pending', 'reasons': ['A frozen protocol manifest is required.']}
    try:
        cases = _cases(manifest)
    except ValueError as error:
        reasons.append(str(error))
        cases = {}
    if (
        manifest.get('reference_reviewed') is not True
        or not cases
        or any(not case.get('reference_hash') for case in cases.values())
    ):
        reasons.append('Human-reviewed reference and its hash are required.')
    targets = manifest.get('targets')
    if manifest.get('targets_approved') is not True or not isinstance(targets, dict) or not targets:
        reasons.append('Advisor-approved numeric acceptance targets are required.')
    elif any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not 0 <= v <= 1
        for v in targets.values()
    ):
        reasons.append('Acceptance targets must be finite numbers in [0, 1].')
    elif set(targets) - {'precision', 'recall', 'f1'}:
        reasons.append('Acceptance targets currently support only precision, recall and f1.')
    budgets = manifest.get('budgets')
    if not isinstance(budgets, dict) or any(
        not isinstance(budgets.get(k), (int, float))
        or isinstance(budgets.get(k), bool)
        or budgets[k] <= 0
        for k in ('max_calls', 'max_steps', 'max_tokens')
    ):
        reasons.append('Shared positive tool, step and token budgets are required.')
    else:
        try:
            from .contracts import RunLimits

            RunLimits(**budgets)
        except (ValueError, TypeError):
            reasons.append('Budget names and types must match RunLimits.')
    if (
        not cases
        or any(not case.get('source_hash') for case in cases.values())
        or any(not case.get('schema_hash') for case in cases.values())
        or manifest.get('split') != 'held_out'
    ):
        reasons.append('Frozen held-out row-content and schema hashes are required for every case.')
    if not cases or any(not case.get('baseline_hash') for case in cases.values()):
        reasons.append('A frozen static-baseline rule-file hash is required for every case.')
    if manifest.get('cache_disabled_attested') is not True or not manifest.get('cache_attestor'):
        reasons.append('An operator attestation that response caching is disabled is required.')
    if not manifest.get('provider') or not manifest.get('resolved_model'):
        reasons.append('Frozen provider and resolved model IDs are required.')
    if manifest.get('runtime_contract') != runtime_contract():
        reasons.append('Runtime code or privacy settings differ from the frozen contract.')
    frozen = _timestamp(manifest.get('frozen_at'))
    if frozen is None or not manifest.get('reviewer') or not manifest.get('protocol_version'):
        reasons.append('Freeze timestamp, reviewer and protocol version are required.')
    if 'manifest_hash' in manifest and manifest['manifest_hash'] != _digest(manifest):
        reasons.append('Frozen manifest content changed after freezing.')
    counts = {'B': 0, 'C': 0}
    case_counts = {case_id: {'B': 0, 'C': 0} for case_id in cases}
    if trials is not None:
        ids = set()
        for run in trials:
            if not isinstance(run, dict):
                continue
            approach, run_id = run.get('approach'), run.get('run_id')
            case_id = run.get('case_id', 'default')
            if not isinstance(case_id, str) or case_id not in cases:
                continue
            case = cases.get(case_id, {})
            started = _timestamp(run.get('started_at'))
            source_identity = run.get('source_identity')
            if not isinstance(source_identity, dict):
                source_identity = {}
            human_review = run.get('human_review')
            if not isinstance(human_review, dict):
                human_review = {}
            usage = run.get('usage')
            if not isinstance(usage, dict):
                usage = {}
            valid = (
                isinstance(approach, str)
                and approach in counts
                and run.get('split') == 'held_out'
                and isinstance(run_id, str)
                and bool(run_id)
                and run_id not in ids
                and run.get('cached') is False
                and (
                    not manifest.get('manifest_hash')
                    or (
                        usage.get('cache_usage_known') is True
                        and type(usage.get('cached_tokens')) is int
                        and usage['cached_tokens'] == 0
                    )
                )
                and run.get('provider') not in {None, '', 'synthetic', 'demo', 'offline-test'}
                and bool(run.get('model'))
                and run.get('status') == 'completed'
                and case_id in case_counts
                and run.get('source_hash') == case.get('source_hash')
                and source_identity.get('source_hash') == case.get('source_hash')
                and run.get('source_hash_after') == case.get('source_hash')
                and run.get('reference_hash') == case.get('reference_hash')
                and source_identity.get('schema_hash') == case.get('schema_hash')
                and (not manifest.get('provider') or run.get('provider') == manifest['provider'])
                and (
                    not manifest.get('resolved_model')
                    or run.get('model') == manifest['resolved_model']
                )
                and run.get('runtime_contract') == manifest.get('runtime_contract')
                and (
                    not manifest.get('manifest_hash')
                    or run.get('manifest_hash') == manifest['manifest_hash']
                )
                and (
                    not manifest.get('manifest_hash')
                    or (
                        isinstance(run.get('original_metrics'), dict)
                        and isinstance(run.get('reviewed_metrics'), dict)
                        and bool(human_review.get('reviewer'))
                        and _trial_measurement_valid(run)
                    )
                )
                and run.get('budgets') == budgets
                and frozen is not None
                and started is not None
                and started > frozen
            )
            if valid:
                counts[approach] += 1
                case_counts[case_id][approach] += 1
                ids.add(run_id)
        for case_id, group in case_counts.items():
            for approach, count in group.items():
                if count < 3:
                    reasons.append(
                        f'Case {case_id}, approach {approach} needs at least 3 distinct uncached completed provider trials after freeze ({count} eligible).'
                    )
    return {
        'status': 'pending' if reasons else 'ready',
        'reasons': reasons,
        'eligible_trials': counts,
        'eligible_trials_by_case': case_counts,
    }


def _eligible_summary_run(run):
    return (
        isinstance(run, dict)
        and run.get('provider') not in {None, '', 'synthetic', 'demo', 'offline-test'}
        and run.get('split') != 'development'
        and run.get('cached') is False
        and run.get('status') == 'completed'
        and bool(run.get('run_id'))
    )


def _summarize_trials(trials, metric_field='metrics'):
    """Sample mean/stdev across completed uncached real trials, retaining N/A."""
    approaches = {}
    excluded = 0
    ids = set()
    for run in trials:
        run_id = run.get('run_id')
        if not _eligible_summary_run(run) or run_id in ids:
            excluded += 1
            continue
        ids.add(run_id)
        group = approaches.setdefault(run.get('approach', 'unknown'), {'trials': 0, 'values': {}})
        group['trials'] += 1
        for key in (
            'precision',
            'recall',
            'f1',
            'tp',
            'fp',
            'fn',
            'predicted_count',
            'reference_count',
        ):
            value = (run.get(metric_field) or {}).get(key)
            values = group['values'].setdefault(key, [])
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
                and (value <= 1 if key in {'precision', 'recall', 'f1'} else type(value) is int)
            ):
                values.append(value)
    for group in approaches.values():
        for key, values in group.pop('values').items():
            group[key] = {
                'n': len(values),
                'mean': statistics.mean(values) if values else None,
                'stdev': statistics.stdev(values) if len(values) > 1 else None,
            }
    return {'approaches': approaches, 'excluded_trials': excluded}


def summarize_efficiency(trials):
    """Known values only; missing usage/cost/review time never becomes zero."""
    groups, seen = {}, set()
    for run in trials:
        if not _eligible_summary_run(run) or run['run_id'] in seen:
            continue
        seen.add(run['run_id'])
        usage = run.get('usage')
        if not isinstance(usage, dict):
            usage = {}
        human_review = run.get('human_review')
        if not isinstance(human_review, dict):
            human_review = {}
        values = {
            'elapsed_seconds': run.get('elapsed_seconds'),
            'tool_calls': usage.get('tool_calls', run.get('tool_calls')),
            'total_tokens': usage.get('total_tokens') if usage.get('usage_known') is True else None,
            'cost_usd': usage.get('cost_usd') if usage.get('usage_known') is True else None,
            'review_seconds': human_review.get('review_seconds'),
        }
        group = groups.setdefault(run.get('approach', 'unknown'), {key: [] for key in values})
        for key, value in values.items():
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                group[key].append(value)
    return {
        approach: {
            key: {
                'n': len(values),
                'mean': statistics.mean(values) if values else None,
                'stdev': statistics.stdev(values) if len(values) > 1 else None,
            }
            for key, values in group.items()
        }
        for approach, group in groups.items()
    }


def summarize_trials(trials):
    """Preserve original and reviewed scores separately, including per-case means."""
    trials = [run for run in trials if isinstance(run, dict)]
    output = _summarize_trials(trials)
    output['original'] = _summarize_trials(trials, 'original_metrics')['approaches']
    output['reviewed'] = _summarize_trials(trials, 'reviewed_metrics')['approaches']
    output['efficiency'] = summarize_efficiency(trials)
    output['proposal_quality'] = summarize_proposal_quality(trials)
    output['by_error_type'] = summarize_error_types(trials)
    output['cases'] = {}
    for case_id in sorted({run.get('case_id', 'default') for run in trials}):
        subset = [run for run in trials if run.get('case_id', 'default') == case_id]
        output['cases'][case_id] = {
            'original': _summarize_trials(subset, 'original_metrics')['approaches'],
            'reviewed': _summarize_trials(subset, 'reviewed_metrics')['approaches'],
            'efficiency': summarize_efficiency(subset),
            'proposal_quality': summarize_proposal_quality(subset),
            'by_error_type': summarize_error_types(subset),
        }
    return output


def summarize_proposal_quality(trials):
    groups, seen = {}, set()
    fields = {
        'rules': (
            'total',
            'correct',
            'incorrect',
            'applicable',
            'useful',
            'correct_rate',
            'covered_reference_rules',
            'reference_rules',
            'reference_coverage',
        ),
        'documentation': (
            'total',
            'supported',
            'unsupported_claims',
            'abstentions',
            'supported_columns',
            'reference_columns',
            'supported_coverage',
        ),
    }
    for run in trials:
        if not _eligible_summary_run(run) or run['run_id'] in seen:
            continue
        seen.add(run['run_id'])
        group = groups.setdefault(
            run.get('approach', 'unknown'),
            {
                'assessed_trials': 0,
                'unassessed_trials': 0,
                **{section: {key: [] for key in keys} for section, keys in fields.items()},
            },
        )
        quality = run.get('proposal_quality')
        if not isinstance(quality, dict):
            quality = {}
        if quality.get('status') != 'complete':
            group['unassessed_trials'] += 1
            continue
        group['assessed_trials'] += 1
        for section, keys in fields.items():
            for key in keys:
                value = quality.get(section, {}).get(key)
                if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                    group[section][key].append(value)
    for group in groups.values():
        for section, keys in fields.items():
            for key in keys:
                values = group[section][key]
                group[section][key] = {
                    'n': len(values),
                    'mean': statistics.mean(values) if values else None,
                    'stdev': statistics.stdev(values) if len(values) > 1 else None,
                }
    return groups


def summarize_error_types(trials):
    output = {}
    for stage in ('original', 'reviewed'):
        types = set()
        for run in trials:
            breakdowns = run.get('detection_breakdown')
            breakdown = breakdowns.get(stage) if isinstance(breakdowns, dict) else None
            if _eligible_summary_run(run) and isinstance(breakdown, dict):
                types.update(breakdown)
        output[stage] = {}
        for name in sorted(types):
            subset = [
                {**run, 'metrics': run['detection_breakdown'][stage][name]}
                for run in trials
                if isinstance(run.get('detection_breakdown'), dict)
                and isinstance(run['detection_breakdown'].get(stage), dict)
                and name in run['detection_breakdown'][stage]
            ]
            output[stage][name] = _summarize_trials(subset)['approaches']
    return output


def measurement_readiness(manifest, trials):
    """Final detection counts alone do not establish all PRD measurements."""
    counts = {case: {'B': 0, 'C': 0} for case in _cases(manifest)}
    seen = set()
    for run in trials:
        if not isinstance(run, dict):
            continue
        case, approach = run.get('case_id', 'default'), run.get('approach')
        human_review = run.get('human_review')
        review_time = human_review.get('review_seconds') if isinstance(human_review, dict) else None
        breakdown = run.get('detection_breakdown')
        if not isinstance(breakdown, dict):
            breakdown = {}
        quality = run.get('proposal_quality')
        if (
            not _eligible_summary_run(run)
            or run['run_id'] in seen
            or case not in counts
            or approach not in counts[case]
        ):
            continue
        seen.add(run['run_id'])
        if (
            isinstance(quality, dict)
            and quality.get('status') == 'complete'
            and isinstance(breakdown.get('original'), dict)
            and isinstance(breakdown.get('reviewed'), dict)
            and type(review_time) in (int, float)
            and math.isfinite(review_time)
            and 0 <= review_time <= 86400
        ):
            counts[case][approach] += 1
    reasons = [
        f'Case {case}, approach {approach} needs 3 trials with original-proposal assessments, '
        f'error-type mappings, and recorded review time ({count} complete).'
        for case, approaches in counts.items()
        for approach, count in approaches.items()
        if count < 3
    ]
    return {
        'status': 'pending' if reasons else 'ready',
        'reasons': reasons,
        'complete_trials_by_case': counts,
        'effort_comparison': 'No reduced-effort claim without a measured comparable baseline.',
    }


def freeze_manifest(manifest, destination):
    """Write once after validation. Existing files cannot be silently overwritten."""
    frozen = json.loads(json.dumps(manifest, allow_nan=False))
    frozen['frozen_at'] = datetime.now(timezone.utc).isoformat()
    frozen['runtime_contract'] = runtime_contract()
    readiness = validate_freeze(frozen)
    if readiness['status'] != 'ready':
        raise ValueError(' '.join(readiness['reasons']))
    from .contracts import RunLimits

    frozen['budgets'] = asdict(RunLimits(**frozen['budgets']))
    frozen['manifest_hash'] = _digest(frozen)
    with Path(destination).open('x', encoding='utf-8') as handle:
        json.dump(frozen, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return frozen


def run_baseline(source, baseline, limits=None):
    """Execute operator-supplied static configurations against a read-only source."""
    from .contracts import RunLimits
    from .quality import summarize_results, validate_rule

    limits = limits or RunLimits()
    started = time.monotonic()
    if (
        not isinstance(baseline, dict)
        or not isinstance(baseline.get('rules'), list)
        or len(baseline['rules']) > 100
    ):
        raise ValueError('Baseline requires at most 100 explicit rules.')
    schema = source.get_schema()
    definitions, ids = [], set()
    # Validate the entire configuration before performing any metric queries.
    for item in baseline['rules']:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get('rule_id'), str)
            or not item['rule_id']
            or item['rule_id'] in ids
        ):
            raise ValueError('Baseline rule IDs must be unique nonempty strings.')
        rule = validate_rule({k: v for k, v in item.items() if k != 'rule_id'}, schema)
        if rule['metric_id'] == 'profile':
            raise ValueError('Profiles are not baseline quality rules.')
        ids.add(item['rule_id'])
        definitions.append((item['rule_id'], rule))
    results, detections = [], []
    status = 'awaiting_human_review'
    for rule_id, rule in definitions:
        if len(results) + 1 >= limits.max_calls or time.monotonic() - started >= limits.max_seconds:
            status = 'budget_exhausted'
            break
        output = source.run_metric(rule['metric_id'], rule['target'], rule['parameters'])
        output = {**output, 'rule_id': rule_id}
        results.append(output)
        if output.get('status') not in {'completed', 'not_applicable', 'no_eligible_data'}:
            status = 'failed'
        if output.get('status') == 'completed' and output.get('violations', 0) != len(
            output.get('violation_ids', [])
        ):
            status = 'incomplete_detections'
        if output.get('status') == 'completed':
            for row_id in output.get('violation_ids', []):
                detections.append(
                    {
                        'rule_id': rule_id,
                        'row_id': row_id,
                        'target': rule['target']['table'] + '.' + rule['target']['column'],
                    }
                )
        if time.monotonic() - started >= limits.max_seconds:
            status = 'budget_exhausted'
            break
    return {
        'approach': 'A',
        'status': status,
        'rules': baseline['rules'],
        'results': results,
        'summary': summarize_results(results),
        'detections': detections,
        'elapsed_seconds': time.monotonic() - started,
        'tool_calls': len(results) + 1,
    }


def complete_baseline(artifact, review, reference, manifest):
    """Score frozen static rules using measured outputs and explicit human mapping."""
    from .evaluation_review import detection_breakdown, reference_catalog, target_name

    case = _cases(manifest).get(artifact.get('case_id', 'default'))
    if (
        case is None
        or artifact.get('approach') != 'A'
        or artifact.get('status') != 'awaiting_human_review'
        or artifact.get('split') != 'held_out'
        or artifact.get('manifest_hash') != manifest.get('manifest_hash')
        or artifact.get('runtime_contract') != manifest.get('runtime_contract')
        or artifact.get('source_hash') != case['source_hash']
        or artifact.get('source_hash_after') != case['source_hash']
        or artifact.get('source_identity', {}).get('schema_hash') != case['schema_hash']
        or artifact.get('source_identity', {}).get('source_hash') != case['source_hash']
        or artifact.get('baseline_hash') != case['baseline_hash']
        or artifact.get('reference_hash') != case['reference_hash']
        or artifact.get('provider') != 'static'
        or artifact.get('model') is not None
        or artifact.get('cached') is not False
        or artifact.get('budgets') != manifest.get('budgets')
        or validate_freeze(manifest)['status'] != 'ready'
        or _timestamp(artifact.get('started_at')) is None
        or _timestamp(artifact.get('started_at')) <= _timestamp(manifest.get('frozen_at'))
        or json_hash(reference) != case['reference_hash']
        or not isinstance(review, dict)
        or not review.get('reviewer')
        or review.get('reference_hash') != case['reference_hash']
        or review.get('artifact_run_id') != artifact.get('run_id')
        or review.get('baseline_hash') != case['baseline_hash']
        or type(review.get('review_seconds')) not in (int, float)
    ):
        raise ValueError('Baseline review does not match the frozen source, rules and reference.')
    from .evaluation_review import validate_review_duration

    validate_review_duration(review)
    rules = artifact.get('rules')
    results = artifact.get('results')
    if (
        not isinstance(rules, list)
        or not isinstance(results, list)
        or json_hash({'rules': rules}) != case['baseline_hash']
        or len(results) != len(rules)
    ):
        raise ValueError('Frozen baseline rules or results changed.')
    catalog, _ = reference_catalog(reference)
    rule_by_id = {rule['rule_id']: rule for rule in rules}
    mappings = review.get('rule_mappings')
    if (
        len(rule_by_id) != len(rules)
        or not isinstance(mappings, dict)
        or set(mappings) != set(rule_by_id)
    ):
        raise ValueError('Map every frozen baseline rule exactly once.')
    for rule_id, target_id in mappings.items():
        if target_id is not None and (
            target_id not in catalog
            or catalog[target_id]['target'] != target_name(rule_by_id[rule_id]['target'])
            or catalog[target_id]['metric_id'] != rule_by_id[rule_id]['metric_id']
        ):
            raise ValueError('Baseline mappings must match reference metrics and targets.')
    measured, mapped = [], []
    seen = set()
    for result in results:
        rule_id = result.get('rule_id')
        if rule_id not in rule_by_id or rule_id in seen:
            raise ValueError('Baseline result IDs changed.')
        seen.add(rule_id)
        target = target_name(rule_by_id[rule_id]['target'])
        if (
            result.get('metric_id') != rule_by_id[rule_id]['metric_id']
            or target_name(result.get('target')) != target
            or result.get('status') not in {'completed', 'no_eligible_data'}
            or result.get('violations') != len(result.get('violation_ids', []))
        ):
            raise ValueError('Baseline detections are incomplete or inconsistent.')
        for row_id in result['violation_ids']:
            measured.append({'rule_id': rule_id, 'row_id': row_id, 'target': target})
            mapped.append(
                {
                    'rule_id': mappings[rule_id] or f'__unmapped__:baseline:{rule_id}',
                    'row_id': row_id,
                    'target': target,
                }
            )
    if {_detection_key(item) for item in measured} != {
        _detection_key(item) for item in artifact.get('detections', [])
    }:
        raise ValueError('Baseline detections differ from its recorded rule results.')
    scores = detection_metrics(mapped, reference['detections'])
    breakdown = detection_breakdown(mapped, reference)
    output = json.loads(json.dumps(artifact, allow_nan=False))
    output.update(
        status='completed',
        mapped_detections=mapped,
        metrics=scores,
        original_metrics=scores,
        reviewed_metrics=None,
        detection_breakdown={'original': breakdown, 'reviewed': None},
        baseline_review=json.loads(json.dumps(review, allow_nan=False)),
        human_review={'reviewer': review['reviewer'], 'review_seconds': review['review_seconds']},
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )
    return output


def verify_completed_baseline(run, reference, manifest):
    if run.get('status') != 'completed':
        return False
    try:
        pending = json.loads(json.dumps(run, allow_nan=False))
        pending['status'] = 'awaiting_human_review'
        replay = complete_baseline(pending, run['baseline_review'], reference, manifest)
        return all(
            run.get(field) == replay.get(field)
            for field in (
                'mapped_detections',
                'metrics',
                'original_metrics',
                'reviewed_metrics',
                'detection_breakdown',
            )
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def run_trial(source, client, approach, manifest, case_id='default'):
    """Record original B/C proposals; no generated rule is automatically executed."""
    from .agent import run_inspection
    from .contracts import RunLimits

    readiness = validate_freeze(manifest)
    if (
        readiness['status'] != 'ready'
        or not manifest.get('manifest_hash')
        or approach not in {'B', 'C'}
    ):
        raise ValueError('Trial requires a ready frozen protocol and approach B or C.')
    budgets = manifest['budgets']
    case = _cases(manifest).get(case_id)
    if case is None:
        raise ValueError('Trial case is not frozen in this protocol.')
    begin_evaluation_snapshot(source)
    identity = source_identity(source)
    if identity['schema_hash'] != case['schema_hash']:
        raise ValueError('Schema identity changed after freeze.')
    if identity['source_hash'] != case['source_hash']:
        raise ValueError('Source row content changed after freeze.')
    if client.provider != manifest['provider'] or client.model != manifest['resolved_model']:
        raise ValueError('Provider configuration changed after freeze.')
    limits = RunLimits(**budgets)
    started = datetime.now(timezone.utc).isoformat()
    inspection = run_inspection(source, client, 'fixed' if approach == 'B' else 'agent', limits)
    after = source_identity(source)
    if after != identity:
        raise ValueError('Source changed during the trial.')
    if (
        inspection['provider'] != manifest['provider']
        or inspection['model'] != manifest['resolved_model']
    ):
        raise ValueError('Resolved provider model changed during the trial.')
    usage = inspection['usage']
    return {
        'run_id': str(uuid.uuid4()),
        'case_id': case_id,
        'split': 'held_out',
        'approach': approach,
        'started_at': started,
        'status': 'awaiting_human_review' if inspection['status'] == 'completed' else 'failed',
        'inspection_status': inspection['status'],
        'provider': inspection['provider'],
        'model': inspection['model'],
        'cached': bool(usage['cached_tokens']) if usage['cache_usage_known'] else None,
        'source_hash': case['source_hash'],
        'source_hash_after': after['source_hash'],
        'reference_hash': case['reference_hash'],
        'source_identity': identity,
        'budgets': dict(budgets),
        'manifest_hash': manifest.get('manifest_hash'),
        'runtime_contract': manifest['runtime_contract'],
        'original_proposals': inspection['proposals'],
        'trace': inspection['trace'],
        'usage': usage,
        'elapsed_seconds': inspection['elapsed_seconds'],
        'profiled_columns': inspection['profiled_columns'],
        'inspected_targets': inspection['inspected_targets'],
    }


def measure_trial(source, artifact, manifest):
    """Execute original rule proposals for research only; never activate them in the app."""
    from .quality import validate_rule

    if (
        artifact.get('status') != 'awaiting_human_review'
        or artifact.get('manifest_hash') != manifest.get('manifest_hash')
        or artifact.get('runtime_contract') != manifest.get('runtime_contract')
        or not manifest.get('manifest_hash')
        or validate_freeze(manifest)['status'] != 'ready'
        or 'original_measurement' in artifact
    ):
        raise ValueError('A pending trial under the unchanged frozen protocol is required.')
    case = _cases(manifest).get(artifact.get('case_id', 'default'))
    if case is None or artifact.get('source_hash') != case['source_hash']:
        raise ValueError('Trial source does not match the frozen case.')
    begin_evaluation_snapshot(source)
    before = source_identity(source)
    if before['source_hash'] != case['source_hash']:
        raise ValueError('Source row content changed after freeze.')
    if before['schema_hash'] != case['schema_hash']:
        raise ValueError('Schema changed after freeze.')
    proposals = artifact.get('original_proposals')
    if not isinstance(proposals, list) or len(proposals) > 100:
        raise ValueError('Original proposals are missing or exceed the safety limit.')
    schema = source.get_schema()
    rules = []
    for index, proposal in enumerate(proposals):
        if proposal.get('kind') == 'rule':
            rule = validate_rule(proposal.get('rule'), schema)
            if rule['target'] != proposal.get('target'):
                raise ValueError('Original proposal target changed.')
            rules.append((index, rule))
    measurements = []
    for index, rule in rules:
        result = source.run_metric(rule['metric_id'], rule['target'], rule['parameters'])
        if result.get('status') not in {'completed', 'no_eligible_data'}:
            raise ValueError('An original rule could not be measured.')
        if result.get('violations') != len(result.get('violation_ids', [])):
            raise ValueError('Original rule detections were truncated; case is ineligible.')
        measurements.append(
            {
                'proposal_index': index,
                'status': result['status'],
                'violations': result['violations'],
                'violation_ids': result['violation_ids'],
            }
        )
    after = source_identity(source)
    if after != before:
        raise ValueError('Source changed during original-rule measurement.')
    measurement = {
        'run_id': artifact['run_id'],
        'source_hash': before['source_hash'],
        'proposals_hash': json_hash(proposals),
        'results': measurements,
    }
    output = json.loads(json.dumps(artifact, allow_nan=False))
    output['original_measurement'] = measurement
    output['original_measurement_hash'] = json_hash(measurement)
    output['measured_at'] = datetime.now(timezone.utc).isoformat()
    return output


def _measured_original_detections(artifact, review):
    from .evaluation_review import target_name

    measurement = artifact.get('original_measurement')
    if measurement is None:
        if review.get('original_detections') is not None:
            raise ValueError('Original detections require executed original-rule measurements.')
        return None
    proposals = artifact['original_proposals']
    if (
        json_hash(measurement) != artifact.get('original_measurement_hash')
        or measurement.get('run_id') != artifact.get('run_id')
        or measurement.get('source_hash') != artifact.get('source_hash')
        or measurement.get('proposals_hash') != json_hash(proposals)
    ):
        raise ValueError('Original-rule measurement provenance changed.')
    expected = {i for i, proposal in enumerate(proposals) if proposal['kind'] == 'rule'}
    results = measurement.get('results')
    if (
        not isinstance(results, list)
        or {r.get('proposal_index') for r in results} != expected
        or len(results) != len(expected)
    ):
        raise ValueError('Every original rule must have one measured result.')
    assessments = {row['proposal_index']: row for row in review['proposal_assessments']}
    detections = []
    for result in results:
        index = result['proposal_index']
        if result.get('violations') != len(result.get('violation_ids', [])):
            raise ValueError('Original-rule detections are incomplete.')
        mapping = assessments[index]['reference_rule_ids']
        rule_ids = mapping or [f'__unmapped__:proposal:{index}']
        target = target_name(proposals[index]['target'])
        for row_id in result['violation_ids']:
            for rule_id in rule_ids:
                detections.append({'rule_id': rule_id, 'row_id': row_id, 'target': target})
    if review.get('original_detections') is not None and {
        _detection_key(item) for item in review['original_detections']
    } != {_detection_key(item) for item in detections}:
        raise ValueError('Original detections must equal measured and mapped outputs.')
    return detections


def complete_trial(artifact, review, reference):
    """Attach human-reviewed rule mapping/detections, keeping original proposals."""
    from .evaluation_review import detection_breakdown, proposal_quality, validate_review_duration

    if (
        not isinstance(review, dict)
        or not isinstance(review.get('reviewer'), str)
        or not review['reviewer'].strip()
        or review.get('reference_hash') != artifact.get('reference_hash')
    ):
        raise ValueError('Review identity and the frozen reference hash are required.')
    if artifact.get('status') != 'awaiting_human_review':
        raise ValueError('Only a successful pending artifact can be reviewed.')
    if json_hash(reference) != artifact.get('reference_hash'):
        raise ValueError('Reference contents changed after freezing.')
    validate_review_duration(review)
    quality = proposal_quality(artifact, review, reference)
    original_detections = (
        _measured_original_detections(artifact, review) if quality['status'] == 'complete' else None
    )
    metrics = detection_metrics(review['detections'], reference['detections'])
    original_metrics = (
        detection_metrics(original_detections, reference['detections'])
        if original_detections is not None
        else None
    )
    output = json.loads(json.dumps(artifact, allow_nan=False))
    output.update(
        {
            'status': 'completed' if original_metrics is not None else 'reviewed_unmeasured',
            'metrics': metrics,
            'reviewed_metrics': metrics,
            'original_metrics': original_metrics,
            'measured_original_detections': original_detections,
            'human_review': json.loads(json.dumps(review, allow_nan=False)),
            'proposal_quality': quality,
            'detection_breakdown': {
                'original': detection_breakdown(original_detections, reference),
                'reviewed': detection_breakdown(review['detections'], reference),
            },
            'reviewed_at': datetime.now(timezone.utc).isoformat(),
        }
    )
    return output


def verify_completed_trial(run, reference):
    """Replay local scoring against the actual frozen reference, not stored scores."""
    if run.get('status') != 'completed' or not _trial_measurement_valid(run):
        return False
    try:
        pending = json.loads(json.dumps(run, allow_nan=False))
        pending['status'] = 'awaiting_human_review'
        replay = complete_trial(pending, run['human_review'], reference)
        fields = (
            'metrics',
            'reviewed_metrics',
            'original_metrics',
            'proposal_quality',
            'detection_breakdown',
            'measured_original_detections',
        )
        return all(run.get(field) == replay.get(field) for field in fields)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def development_pilot(approach, directory, budgets, check_only=False):
    """One unfrozen pilot. Never executes proposed rules or claims final accuracy."""
    from .agent import run_inspection
    from .contracts import RunLimits
    from .providers import create_client
    from .readiness import inspection_readiness
    from .source import MySQLSource

    limits = RunLimits(**budgets)
    mode = {'B': 'fixed', 'C': 'agent'}[approach]
    try:
        source = MySQLSource.from_env()
    except Exception:
        readiness = inspection_readiness(None, None, mode, limits)
        readiness['issues'][0] = {
            'code': 'source_connection',
            'message': 'Could not connect. Check MYSQL_* settings, the selected schema, '
            'server availability, and read-only grants.',
        }
        return {'status': 'pending', 'split': 'development', 'preflight': readiness}
    try:
        schema = source.get_schema()
        readiness = inspection_readiness(schema, 'mysql', mode, limits)
        if check_only or not readiness['ready']:
            return {
                'status': 'ready' if readiness['ready'] else 'pending',
                'split': 'development',
                'preflight': readiness,
            }
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        run_id = str(uuid.uuid4())
        destination = directory / (run_id + '.json')
        client = create_client()
        # Check the destination before spending any provider request budget.
        with destination.open('x', encoding='utf-8') as handle:
            started = datetime.now(timezone.utc).isoformat()
            inspection = run_inspection(source, client, mode, limits)
            artifact = {
                **inspection,
                'run_id': run_id,
                'approach': approach,
                'split': 'development',
                'started_at': started,
                'inspection_status': inspection['status'],
                'status': 'development_completed'
                if inspection['status'] == 'completed'
                else 'failed',
                'original_proposals': inspection['proposals'],
                'preflight': readiness,
            }
            del artifact['proposals']
            json.dump(artifact, handle, indent=2, allow_nan=False)
        return {'status': artifact['status'], 'split': 'development', 'artifact': str(destination)}
    finally:
        source.close()


def main(argv=None):
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / '.env.local')
    load_dotenv(root / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    freeze = commands.add_parser('freeze', help='Validate and freeze a human-reviewed protocol.')
    freeze.add_argument('manifest')
    freeze.add_argument('output')
    evaluate = commands.add_parser(
        'evaluate', help='Evaluate local detection JSON against a reviewed reference.'
    )
    evaluate.add_argument('result')
    evaluate.add_argument('reference')
    final = commands.add_parser('final', help='Validate final repeated trials and summarize them.')
    final.add_argument('manifest')
    final.add_argument('trials')
    final.add_argument(
        'references', nargs='?', help='JSON object mapping each case ID to its reviewed reference.'
    )
    final.add_argument('baselines', nargs='?', help='JSON array of reviewed static baselines.')
    baseline = commands.add_parser(
        'baseline', help='Execute explicitly supplied static rules on configured read-only MySQL.'
    )
    baseline.add_argument('manifest')
    baseline.add_argument('baseline')
    baseline.add_argument('output')
    baseline.add_argument(
        '--source-hash', required=True, help='Verified frozen dataset snapshot hash.'
    )
    baseline.add_argument('--case', default='default')
    baseline_review = commands.add_parser(
        'baseline-review', help='Score frozen static-rule outputs against a reviewed reference.'
    )
    baseline_review.add_argument('manifest')
    baseline_review.add_argument('artifact')
    baseline_review.add_argument('review')
    baseline_review.add_argument('reference')
    baseline_review.add_argument('output')
    trial = commands.add_parser(
        'trial', help='Run B or C provider inspections; retain originals for human review.'
    )
    trial.add_argument('manifest')
    trial.add_argument('approach', choices=['B', 'C'])
    trial.add_argument('directory')
    trial.add_argument(
        '--source-hash', required=True, help='Verified frozen dataset snapshot hash.'
    )
    trial.add_argument('--repeats', type=int, default=3)
    trial.add_argument('--case', default='default')
    pilot = commands.add_parser(
        'pilot', help='One development-only B/C inspection, excluded from final evaluation.'
    )
    pilot.add_argument('approach', choices=['B', 'C'])
    pilot.add_argument('directory')
    pilot.add_argument('--budgets', required=True, help='JSON object containing RunLimits fields.')
    pilot.add_argument('--check-only', action='store_true', help='Check locally; no model request.')
    review = commands.add_parser(
        'review',
        help='Attach human-reviewed detection mapping without changing original proposals.',
    )
    review.add_argument('artifact')
    review.add_argument('review')
    review.add_argument('reference')
    review.add_argument('output')
    measure = commands.add_parser(
        'measure', help='Run original trial rule proposals against frozen read-only MySQL.'
    )
    measure.add_argument('manifest')
    measure.add_argument('artifact')
    measure.add_argument('output')
    template = commands.add_parser(
        'review-template',
        help='Prepare blank human assessments for a pending trial; no model call.',
    )
    template.add_argument('artifact')
    template.add_argument('reference')
    template.add_argument('output')
    hashing = commands.add_parser(
        'hash', help='Hash canonical JSON reference or source snapshot metadata.'
    )
    hashing.add_argument('input')
    commands.add_parser(
        'identity', help='Hash selected MySQL row content and schema without calling a provider.'
    )
    args = parser.parse_args(argv)

    def read(path):
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))

    try:
        if args.command == 'freeze':
            output = freeze_manifest(read(args.manifest), args.output)
        elif args.command == 'evaluate':
            predicted, reference = read(args.result), read(args.reference)
            output = {
                'status': 'exploratory',
                'metrics': detection_metrics(predicted['detections'], reference['detections']),
            }
        elif args.command == 'final':
            manifest, trials = read(args.manifest), read(args.trials)
            if not isinstance(manifest, dict) or not isinstance(trials, list):
                raise ValueError('Final evaluation requires a frozen manifest and a trial array.')
            references = read(args.references) if args.references else None
            frozen_cases = _cases(manifest)
            references_complete = isinstance(references, dict) and set(references) == set(
                frozen_cases
            )
            if not references_complete:
                references = {}
            verified = []
            for run in trials:
                if not isinstance(run, dict):
                    continue
                case_id = run.get('case_id', 'default')
                if not isinstance(case_id, str):
                    continue
                reference = references.get(case_id)
                case = frozen_cases.get(case_id)
                if (
                    case is not None
                    and isinstance(reference, dict)
                    and json_hash(reference) == case['reference_hash']
                    and verify_completed_trial(run, reference)
                ):
                    verified.append(run)
            eligible, seen_run_ids = [], set()
            for run in verified:
                run_id = run.get('run_id')
                if (
                    isinstance(run_id, str)
                    and run_id not in seen_run_ids
                    and sum(validate_freeze(manifest, [run])['eligible_trials'].values())
                ):
                    eligible.append(run)
                    seen_run_ids.add(run_id)
            output = validate_freeze(manifest, eligible)
            if not manifest.get('manifest_hash'):
                output['status'] = 'pending'
                output['reasons'].append('Use a manifest produced by the freeze command.')
            if not references_complete:
                output['status'] = 'pending'
                output['reasons'].append('Provide every unchanged human-reviewed case reference.')
            baselines = read(args.baselines) if args.baselines else None
            scored_baselines = []
            if isinstance(baselines, list):
                for run in baselines:
                    if not isinstance(run, dict):
                        continue
                    case_id = run.get('case_id', 'default')
                    if not isinstance(case_id, str):
                        continue
                    reference = references.get(case_id)
                    if (
                        case_id in frozen_cases
                        and isinstance(reference, dict)
                        and verify_completed_baseline(run, reference, manifest)
                    ):
                        scored_baselines.append(run)
            baseline_cases = [run.get('case_id', 'default') for run in scored_baselines]
            if sorted(baseline_cases) != sorted(frozen_cases):
                output['status'] = 'pending'
                output['reasons'].append(
                    'One replayable frozen static baseline is required per case.'
                )
            output['summary'] = summarize_trials(eligible + scored_baselines)
            output['measurement_readiness'] = measurement_readiness(manifest, eligible)
            if output['measurement_readiness']['status'] != 'ready':
                output['status'] = 'pending'
                output['reasons'].extend(output['measurement_readiness']['reasons'])
            output['excluded_frozen_input_trials'] = len(trials) - len(eligible)
            output['excluded_baselines'] = (
                len(baselines) if isinstance(baselines, list) else 0
            ) - len(scored_baselines)
            output['acceptance'] = {}
            for case_id, case_summary in output['summary']['cases'].items():
                metrics = case_summary['original'].get('C', {})
                checks = {
                    name: None
                    if metrics.get(name, {}).get('mean') is None
                    else metrics[name]['mean'] >= target
                    for name, target in manifest.get('targets', {}).items()
                }
                output['acceptance'][case_id] = {
                    'original_agent_targets': checks,
                    'meets_targets': None
                    if not checks or any(v is None for v in checks.values())
                    else all(checks.values()),
                }
                if output['acceptance'][case_id]['meets_targets'] is None:
                    output['status'] = 'pending'
                    output['reasons'].append(f'Case {case_id} has unassessable acceptance targets.')
        elif args.command == 'review-template':
            from .evaluation_review import review_template

            output = review_template(read(args.artifact), read(args.reference))
            with Path(args.output).open('x', encoding='utf-8') as handle:
                json.dump(output, handle, indent=2, allow_nan=False)
        elif args.command == 'review':
            output = complete_trial(read(args.artifact), read(args.review), read(args.reference))
            with Path(args.output).open('x', encoding='utf-8') as handle:
                json.dump(output, handle, indent=2, allow_nan=False)
        elif args.command == 'baseline-review':
            output = complete_baseline(
                read(args.artifact), read(args.review), read(args.reference), read(args.manifest)
            )
            with Path(args.output).open('x', encoding='utf-8') as handle:
                json.dump(output, handle, indent=2, allow_nan=False)
        elif args.command == 'measure':
            from .source import MySQLSource

            source = MySQLSource.from_env()
            try:
                output = measure_trial(source, read(args.artifact), read(args.manifest))
                with Path(args.output).open('x', encoding='utf-8') as handle:
                    json.dump(output, handle, indent=2, allow_nan=False)
            finally:
                source.close()
        elif args.command == 'hash':
            output = {'sha256': json_hash(read(args.input))}
        elif args.command == 'pilot':
            output = development_pilot(
                args.approach, args.directory, read(args.budgets), args.check_only
            )
        elif args.command == 'identity':
            from .source import MySQLSource

            source = MySQLSource.from_env()
            try:
                begin_evaluation_snapshot(source)
                output = source_identity(source)
            finally:
                source.close()
        else:
            from .providers import create_client
            from .source import MySQLSource

            manifest = read(args.manifest)
            case = _cases(manifest).get(args.case)
            if (
                validate_freeze(manifest)['status'] != 'ready'
                or not manifest.get('manifest_hash')
                or not case
                or args.source_hash != case.get('source_hash')
            ):
                raise ValueError('Frozen inputs do not match.')
            if args.command == 'baseline':
                source = MySQLSource.from_env()
                try:
                    from .contracts import RunLimits

                    begin_evaluation_snapshot(source)
                    identity = source_identity(source)
                    if identity['schema_hash'] != case['schema_hash']:
                        raise ValueError('Schema changed after freeze.')
                    if identity['source_hash'] != case['source_hash']:
                        raise ValueError('Source row content changed after freeze.')
                    baseline_input = read(args.baseline)
                    if (
                        set(baseline_input) != {'rules'}
                        or json_hash(baseline_input) != case['baseline_hash']
                    ):
                        raise ValueError('Static baseline changed after freeze.')
                    started_at = datetime.now(timezone.utc).isoformat()
                    output = run_baseline(source, baseline_input, RunLimits(**manifest['budgets']))
                    after = source_identity(source)
                    if after != identity:
                        raise ValueError('Source changed during the baseline.')
                    output.update(
                        {
                            'run_id': str(uuid.uuid4()),
                            'started_at': started_at,
                            'case_id': args.case,
                            'split': 'held_out',
                            'source_hash': case['source_hash'],
                            'baseline_hash': case['baseline_hash'],
                            'source_hash_after': after['source_hash'],
                            'reference_hash': case['reference_hash'],
                            'source_identity': identity,
                            'manifest_hash': manifest['manifest_hash'],
                            'runtime_contract': manifest['runtime_contract'],
                            'budgets': manifest['budgets'],
                            'provider': 'static',
                            'model': None,
                            'cached': False,
                        }
                    )
                    with Path(args.output).open('x', encoding='utf-8') as handle:
                        json.dump(output, handle, indent=2, allow_nan=False)
                finally:
                    source.close()
            else:
                if not 3 <= args.repeats <= 20:
                    raise ValueError('Trial repetitions must be between three and twenty.')
                directory = Path(args.directory)
                directory.mkdir(parents=True, exist_ok=True)
                client = create_client()
                artifacts = []
                for _ in range(args.repeats):
                    source = MySQLSource.from_env()
                    try:
                        artifact = run_trial(source, client, args.approach, manifest, args.case)
                        destination = directory / (artifact['run_id'] + '.json')
                        with destination.open('x', encoding='utf-8') as handle:
                            json.dump(artifact, handle, indent=2, allow_nan=False)
                        artifacts.append(str(destination))
                    finally:
                        source.close()
                output = {'status': 'awaiting_human_review', 'artifacts': artifacts}
        print(json.dumps(output, indent=2, allow_nan=False))
        return 2 if output.get('status') in {'pending', 'failed'} else 0
    except Exception:
        print(
            json.dumps(
                {
                    'status': 'invalid',
                    'message': 'Input is malformed, incomplete, or destination exists.',
                }
            )
        )
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
