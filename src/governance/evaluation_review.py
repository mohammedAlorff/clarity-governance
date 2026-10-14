"""Score explicit human judgments; never infer correctness from approval or wording."""

import math

from .contracts import METRICS


def target_name(value):
    if isinstance(value, dict):
        table, column = value.get('table'), value.get('column')
        if isinstance(table, str) and table and isinstance(column, str) and column:
            return table + '.' + column
    if isinstance(value, str) and value and '.' in value:
        return value
    raise ValueError('Reference targets must identify a table and column.')


def reference_catalog(reference):
    rules, columns = {}, set()
    if not isinstance(reference.get('rules'), list) or not isinstance(
        reference.get('columns'), list
    ):
        raise ValueError('Proposal assessment requires reference rules and the full column scope.')
    for rule in reference['rules']:
        rule_id = rule.get('rule_id')
        if (
            not isinstance(rule_id, str)
            or not rule_id
            or rule_id in rules
            or rule_id.startswith('__unmapped__:')
        ):
            raise ValueError('Reference rule IDs must be unique nonempty strings.')
        if rule.get('metric_id') not in METRICS[1:]:
            raise ValueError('Reference rules require a supported quality metric.')
        rules[rule_id] = {**rule, 'target': target_name(rule.get('target'))}
    for column in reference['columns']:
        target = target_name(column.get('target'))
        if target in columns:
            raise ValueError('Reference columns must be unique.')
        columns.add(target)
    if any(rule['target'] not in columns for rule in rules.values()):
        raise ValueError('Reference rule targets must be in the reference column scope.')
    return rules, columns


def review_template(artifact, reference):
    from .evaluation import json_hash

    if artifact.get('status') != 'awaiting_human_review' or artifact.get(
        'reference_hash'
    ) != json_hash(reference):
        raise ValueError('A pending trial and its unchanged reference are required.')
    measurement = artifact.get('original_measurement')
    if not isinstance(measurement, dict) or artifact.get('original_measurement_hash') != json_hash(
        measurement
    ):
        raise ValueError('Measure original rules before preparing the review form.')
    reference_catalog(reference)
    rows = []
    for index, proposal in enumerate(artifact['original_proposals']):
        row = {'proposal_index': index, 'notes': ''}
        if proposal['kind'] == 'rule':
            row.update(correct=None, applicable=None, useful=None, reference_rule_ids=[])
        elif proposal['kind'] == 'description':
            row.update(supported=None, unsupported_claims=None, abstained=None)
        else:
            raise ValueError('Unknown original proposal kind.')
        rows.append(row)
    return {
        'purpose': 'Human review of original proposals. Fill every judgment explicitly; '
        'do not infer correctness from approval. Enter [] for detections only after checking.',
        'reviewer': None,
        'reference_hash': artifact['reference_hash'],
        'artifact_run_id': artifact['run_id'],
        'original_proposals_hash': json_hash(artifact['original_proposals']),
        'review_seconds': None,
        'original_detections': None,
        'detections': None,
        'proposal_assessments': rows,
    }


def validate_review_duration(review):
    value = review.get('review_seconds')
    if value is not None and (
        type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 86400
    ):
        raise ValueError('Review time must be a finite number from 0 to 86400, or null.')


def proposal_quality(artifact, review, reference):
    from .evaluation import json_hash

    rows = review.get('proposal_assessments')
    if rows is None:
        return {'status': 'pending', 'reason': 'Original proposals have not been assessed.'}
    proposals = artifact.get('original_proposals', [])
    if (
        not artifact.get('run_id')
        or review.get('artifact_run_id') != artifact['run_id']
        or review.get('original_proposals_hash') != json_hash(proposals)
    ):
        raise ValueError('Assessments must match this run and its unchanged original proposals.')
    if not isinstance(rows, list) or len(rows) != len(proposals):
        raise ValueError('Assess every original proposal exactly once.')
    catalog, columns = reference_catalog(reference)
    seen, covered_rules, supported_columns = set(), set(), set()
    rules = {'total': 0, 'correct': 0, 'incorrect': 0, 'applicable': 0, 'useful': 0}
    docs = {'total': 0, 'supported': 0, 'unsupported_claims': 0, 'abstentions': 0}
    for row in rows:
        index = row.get('proposal_index')
        if type(index) is not int or not 0 <= index < len(proposals) or index in seen:
            raise ValueError('Proposal indices must be unique and match the original artifact.')
        seen.add(index)
        proposal = proposals[index]
        target = target_name(proposal['target'])
        if proposal['kind'] == 'rule':
            fields = ('correct', 'applicable', 'useful')
            if any(type(row.get(field)) is not bool for field in fields):
                raise ValueError('Every rule judgment must be an explicit boolean.')
            ids = row.get('reference_rule_ids')
            proposal_rule = proposal.get('rule')
            metric_id = proposal_rule.get('metric_id') if isinstance(proposal_rule, dict) else None
            if (
                not isinstance(ids, list)
                or any(not isinstance(item, str) or item not in catalog for item in ids)
                or len(ids) != len(set(ids))
                or len(ids) > 1
                or any(catalog[item]['target'] != target for item in ids)
                or any(catalog[item]['metric_id'] != metric_id for item in ids)
                or (row['correct'] and row['applicable'] and not ids)
                or (ids and not (row['correct'] and row['applicable']))
            ):
                raise ValueError(
                    'Map each correct applicable rule to one reference rule with the same metric and target.'
                )
            rules['total'] += 1
            for field in fields:
                rules[field] += int(row[field])
            rules['incorrect'] += int(not row['correct'])
            if row['correct'] and row['applicable']:
                covered_rules.update(ids)
        elif proposal['kind'] == 'description':
            fields = ('supported', 'unsupported_claims', 'abstained')
            if any(type(row.get(field)) is not bool for field in fields):
                raise ValueError('Every description judgment must be an explicit boolean.')
            if (row['supported'] and (row['unsupported_claims'] or row['abstained'])) or (
                row['abstained'] and row['unsupported_claims']
            ):
                raise ValueError('Supported, unsupported-claim, and abstention judgments conflict.')
            if row['supported'] and target not in columns:
                raise ValueError('A supported description must belong to the reference scope.')
            docs['total'] += 1
            docs['supported'] += int(row['supported'])
            docs['unsupported_claims'] += int(row['unsupported_claims'])
            docs['abstentions'] += int(row['abstained'])
            if row['supported']:
                supported_columns.add(target)
        else:
            raise ValueError('Unknown original proposal kind.')
    rules.update(
        correct_rate=rules['correct'] / rules['total'] if rules['total'] else None,
        covered_reference_rules=len(covered_rules),
        reference_rules=len(catalog),
        reference_coverage=len(covered_rules) / len(catalog) if catalog else None,
    )
    docs.update(
        supported_columns=len(supported_columns),
        reference_columns=len(columns),
        supported_coverage=len(supported_columns) / len(columns) if columns else None,
    )
    return {
        'status': 'complete',
        'basis': 'human judgments of original proposals',
        'rules': rules,
        'documentation': docs,
    }


def detection_breakdown(predicted, reference):
    from .evaluation import detection_metrics

    if predicted is None or 'rules' not in reference or 'columns' not in reference:
        return None
    catalog, _ = reference_catalog(reference)
    actual = reference['detections']
    for item in actual:
        rule = catalog.get(str(item['rule_id']))
        if rule is None or target_name(item['target']) != rule['target']:
            raise ValueError('Reference detections must match their reference rules.')

    def metric(item):
        return catalog.get(str(item['rule_id']), {}).get('metric_id', 'unmapped')

    types = {rule['metric_id'] for rule in catalog.values()} | {metric(item) for item in predicted}
    return {
        name: detection_metrics(
            [item for item in predicted if metric(item) == name],
            [item for item in actual if metric(item) == name],
        )
        for name in sorted(types)
    }
