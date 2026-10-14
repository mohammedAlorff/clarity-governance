# Review and measurement guide

This guide covers human evaluation of the original model output. Approving a proposal in the application is a workflow decision; it does not automatically mark the proposal correct for an experiment.

## Prepare the reference before freezing

The human-reviewed reference needs `detections`, a `rules` catalog, and the full selected column scope in `columns`. Rule IDs and column targets must be unique. Every rule needs a supported `metric_id` and a target in that column scope. Accepted meanings, business rationale, and applicability should be recorded alongside these fields for the reviewer.

This is a **format example only**, not accepted ground truth:

```json
{
  "rules": [
    {
      "rule_id": "required_customer_id",
      "metric_id": "completeness",
      "target": "orders.customer_id",
      "rationale": "Replace with a human-confirmed requirement."
    }
  ],
  "columns": [
    {"target": "orders.customer_id", "accepted_meaning": "Replace with a reviewed meaning."}
  ],
  "detections": [
    {"rule_id": "required_customer_id", "row_id": 12, "target": "orders.customer_id"}
  ]
}
```

Targets can also be objects with `table` and `column`. Use all selected columns, including ones the model never described, as the coverage denominator. An empty catalog produces N/A coverage, not automatic success. Do not add reference answers to the model input. Finish and hash the complete reference before freezing; changing it later invalidates the trial reference hash.

## Generate a review form

After a successful frozen B/C trial, run the read-only `measure` command from the [evaluation protocol](evaluation.md#human-review-and-metrics). It executes each original rule proposal outside the application approval flow, binds the result to the frozen source hash, and refuses truncated row IDs. Then generate a form locally from that measured artifact:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation review-template data\trials\run-measured.json reference.json data\trials\review.json
```

No source or model is called. This verifies the reference hash and writes a new file without overwriting existing work. Each row refers to the zero-based `proposal_index` in the artifact's immutable `original_proposals`. The form binds to the run ID and a hash of those originals; a form for another run or edited originals is rejected.

Reviewer identity, detection lists, duration, and judgments start as null. A human must enter the decisions. Leave `original_detections` null: it is derived from the measured original rules and the human rule mappings. An empty corrected `detections` list means “checked and found none”; null means “not assessed.” Keep the original artifact open beside the form. Record concise supporting notes for each judgment.

For each original **rule**, enter boolean `correct`, `applicable`, and `useful` judgments against the reference, plus `reference_rule_ids` identifying its equivalent reference rule. A correct, applicable rule must map to exactly one known reference rule with the same target and metric type. Confirm parameter-level equivalence manually against the frozen reference; matching the metric type alone does not prove the checks have identical thresholds or accepted values. These judgments are independent: a valid rule may add little practical value. Duplicate equivalent proposals count separately as proposals but cover a reference rule only once.

For each original **description**, enter boolean `supported`, `unsupported_claims`, and `abstained` judgments. A supported description must be grounded in the reference and contain no unsupported claims. Abstention means the proposal declines to assert a meaning; it is counted explicitly and does not count as a supported description. Supported, unsupported-claim, and abstention judgments are mutually exclusive; all false allows an incorrect or unsubstantiated answer without claiming a verified unsupported assertion. Record the reasoning in notes. Equivalent wording is acceptable when the factual meaning is supported.

Enter `detections` for the result after human corrections. Preserve reference rule IDs, stable row IDs, and targets. The scorer derives `original_detections` from actual read-only check results and the assessed mappings; if a reviewer also supplies this field, it must exactly match the derived set. A proposal without a mapping receives a reserved `__unmapped__:` ID, so its violations can only contribute false positives. Do not substitute the reference detections for measured outputs. Record actual `review_seconds` between 0 and 86,400; leave null if unmeasured. Time includes whatever review procedure the frozen protocol specifies and should use the same procedure across B and C.

Attach the completed review:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation review data\trials\run-measured.json data\trials\review.json reference.json data\trials\reviewed.json
```

Missing, duplicate, invalid, contradictory, or mismatched assessments are rejected. The output keeps original proposals unchanged and stores the human review separately. Legacy reviews without executed original-rule measurements remain `reviewed_unmeasured` and cannot count as completed formal trials.

## Read the measurements

- Rule quality reports total, correct, incorrect, applicable, and useful proposals. Correct rate divides correct proposals by all rule proposals. Reference coverage divides unique reference rules covered by correct applicable proposals by all reference rules.
- Documentation reports supported descriptions, unsupported claims, and abstentions. Supported coverage divides distinct columns with a supported description by the full reference column scope.
- Detection scores retain TP, FP, FN, precision, recall, and F1 for original and reviewed outputs, overall and by metric/error type. Predictions with unknown reference rule IDs appear in an `unmapped` group and still count as false positives. Undefined denominators remain null.
- Efficiency reports per-approach and per-case mean, sample standard deviation, and the number of known observations for elapsed seconds, tool calls, tokens, estimated cost, and review time. Unknown usage, prices, and durations remain missing. Price estimates do not establish actual billing. Differences in review time do not establish reduced effort without a comparable measured baseline.

Final summaries include proposal-quality distributions and assessed/unassessed trial counts. They require at least three eligible B and three eligible C trials per frozen case with assessments, error-type mappings, and measured review time before marking the full measurement set ready. Unknown token costs remain visibly unknown. Development runs, cached results, duplicate run IDs, and other ineligible trials stay excluded.

These calculations summarize human judgments; they do not verify reviewer identity, establish inter-rater agreement, or prove the reference is correct. The file hashes and replay checks are not authentication signatures: a person with write access can alter a raw measurement and recompute its hash. Preserve raw artifacts and a controlled custody record, or independently rerun measurements on the frozen source, before making tamper-resistance claims. State these limitations in the final report.
