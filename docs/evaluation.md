# Evaluation protocol

An [exploratory six-run Codex proxy](../evaluation/codex-pilot/README.md)
records what an older GPT model proposed on the isolated public-data fault
fixture while the local Qwen service stayed off and no OpenAI API key was
created. Its development-only artifacts and exact-configuration technical
scores are separate from the formal application-provider protocol below; they
do not replace a human-reviewed held-out comparison.

The application and its synthetic demo establish the workflow. They do not establish that an adaptive agent improves accuracy or review effort. A final result needs an independently designed held-out schema, a human-reviewed reference, and a frozen protocol before the held-out run.

## Development pilot before freezing

Use the configured read-only public MySQL source to try the fixed (B) and adaptive (C) workflows before selecting final budgets. `evaluation/pilot/run-budgets.json` is an editable development example: 100 calls, 8 steps, 120 seconds, 64,000 total tokens, 4,000 output tokens per request, and one retry. It allows the 91-call Sakila profiling pass but does not guarantee adequate time or tokens. These are unapproved development settings, not final acceptance targets.

Check local readiness without a model request:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation pilot B data\pilot-runs --budgets evaluation\pilot\run-budgets.json --check-only
```

This command opens the configured read-only source to inspect metadata and validates local provider/privacy configuration. Missing settings return `pending` and exit code 2. It neither creates a provider client nor writes an artifact. Credentials and model availability remain unverified.

With the selected provider configured and available, run one pilot at a time. The local Qwen workflow needs its local server running; optional cloud providers can incur API charges:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation pilot B data\pilot-runs --budgets evaluation\pilot\run-budgets.json
.\.venv\Scripts\python.exe -m governance.evaluation pilot C data\pilot-runs --budgets evaluation\pilot\run-budgets.json
```

Each writes a unique JSON artifact containing original proposals, effective limits, provider/model, privacy audit, sanitized trace, usage, and outcome. Proposed rules are not executed. A failed/exhausted inspection retains its artifact and exits 2. Setup/preflight metadata reads are outside the recorded inspection budget. Artifacts carry `split: development` and are explicitly excluded from final trial counts and summaries, even if other fields happen to match a frozen protocol. Pilot completion is not a measured accuracy result; use separate held-out data and human review for that.

## Freeze the final protocol

Create a JSON manifest with these fields, then freeze it once with the evaluation utility:

```json
{
  "protocol_version": "1",
  "reviewer": "advisor-or-reviewer-id",
  "reference_reviewed": true,
  "reference_hash": "sha256-of-reviewed-reference",
  "targets_approved": true,
  "targets": {"precision": 0.8, "recall": 0.8},
  "provider": "local",
  "resolved_model": "qwen3-4b-instruct-2507",
  "source_hash": "sha256-of-held-out-snapshot",
  "schema_hash": "sha256-of-held-out-schema",
  "baseline_hash": "sha256-of-static-baseline-json",
  "cache_disabled_attested": true,
  "cache_attestor": "operator-who-disabled-response-caching",
  "split": "held_out",
  "budgets": {"max_calls": 40, "max_steps": 8, "max_seconds": 60, "max_tokens": 16000, "max_output_tokens": 3000, "max_retries": 1},
  "cases": [
    {"case_id": "case-01", "source_hash": "sha256-of-case-snapshot", "schema_hash": "sha256-of-case-schema", "baseline_hash": "sha256-of-case-static-rules", "reference_hash": "sha256-of-case-reference"}
  ]
}
```

Get the required `source_hash` and `schema_hash` for each selected read-only MySQL case with `python -m governance.evaluation identity` after loading that case's `MYSQL_*` settings. The source hash streams selected rows locally and fails closed at one million rows, five minutes, or an oversized row; a server-side size check precedes row transfer. The identity, baseline, trial, and measurement commands hold a consistent read-only MySQL snapshot while they inspect a case. Only hashes leave the snapshot routine. Hash the final static-rule JSON with `python -m governance.evaluation hash baseline.json` and store that value as `baseline_hash`; the baseline command refuses later edits. The operator must actually disable response caching for the selected provider/server before attesting this in the manifest. A reported zero prompt-cache token count alone cannot prove that all response caches were disabled. The reference must contain accepted column meanings, confirmed rules, stable row IDs, and a manifest of known violations. Include clean data, meaningful names, obscured names, and cases where the evidence cannot identify a unique meaning. Keep the reference and final error locations out of the agent prompt. Record which clues remain visible in every obscured case.

Freeze it with:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation freeze protocol.json frozen.json
```

The utility writes once and adds a manifest hash and nonsecret runtime contract. That contract fingerprints the prompt, tool schemas, rule engine, privacy code, provider adapters, and active sampling settings. It refuses incomplete prerequisites or overwriting an existing frozen file. Do not change prompts, model/version, tool schemas, source snapshots, rule definitions, budgets, targets, or scoring weights after this step. Provider-side settings and the exact local model artifact/version must also be recorded by the study operator; a model name alone cannot prove immutable weights.

## The three variants

Variant A is the fixed, documented rules baseline. Put only operator-authored rules in `baseline.json`; each rule needs a unique `rule_id`, a validated metric, target, and parameters. Freeze its file hash before seeing held-out results. It executes read-only checks and preserves detections for human mapping:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation baseline frozen.json baseline.json artifacts\baseline.json --source-hash <frozen-source-hash>
```

Have a human map every baseline rule ID to an equivalent reference rule ID or `null`, with reviewer identity and measured review time. The review JSON contains `reviewer`, `review_seconds`, `artifact_run_id`, `reference_hash`, `baseline_hash`, and `rule_mappings`. Score A without changing its measured rows:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation baseline-review frozen.json artifacts\baseline.json baseline-review.json reference.json artifacts\baseline-scored.json
```

Variant B uses the same configured model and tools as C with a predetermined inspection sequence. Variant C uses the bounded agent to choose later inspections from observed results. Both must have the same information sources and maximum budgets. Run each at least three times for every frozen case with response caching disabled:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation trial frozen.json B artifacts\B --source-hash <frozen-source-hash> --repeats 3
.\.venv\Scripts\python.exe -m governance.evaluation trial frozen.json C artifacts\C --source-hash <frozen-source-hash> --repeats 3
```

The trial command opens a read-only MySQL connection per run, checks the row-content fingerprint before and after inspection, and records the source/reference hashes, model and provider IDs, limits, actual usage, elapsed time, sanitized trace, and original proposals. It does not approve or execute proposed business rules. If the provider does not report cache usage, the artifact remains ineligible for an independent uncached trial; the local adapter keeps absent cache metadata unknown rather than treating it as zero.

## Human review and metrics

Measure each original rule proposal separately on the unchanged frozen read-only source before review. This research command does not approve or activate rules in the application and does not call the model:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation measure frozen.json artifacts\<run>.json artifacts\<run>-measured.json
```

The command writes a new artifact, records complete violation IDs by proposal index, and refuses truncated detections or changed row content. This separate scoring measurement is external evaluation overhead; its queries and time are not included in B/C agent inspection budgets or agent elapsed time. Report it separately if comparing total end-to-end study effort with A. Use the [review and measurement guide](evaluation-review.md) to prepare the complete reference catalog, generate a blank review form from the **measured** artifact, and record rule/documentation judgments. The `review-template` command performs no source or provider calls and never pre-fills human decisions.

Review each original proposal for correctness, applicability, usefulness, and reference coverage. Review documentation for factual correctness, unsupported claims, abstentions, and supported-description coverage. Record human corrections separately from original model output. Approval is a workflow decision, not proof of correctness.

Map equivalent proposed checks to the human reference. The utility derives original detections from the measured rule results and reviewer-supplied rule mappings; manually entered row IDs cannot create an original-agent detection. A detection key is `(reference rule ID, stable row ID, target)`. The utility reports raw TP/FP/FN and precision, recall, and F1; zero-denominator metrics remain N/A. Report results by error type and overall. Measure model cost (only when published unit prices are configured), elapsed time, tool calls, token usage, and human review time. A reduced-effort claim needs a comparable manual or baseline task.

Attach a reviewed detection mapping only after the artifact is available:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation review artifacts\<run>-measured.json human-review.json reference.json artifacts\<run>-reviewed.json
```

Summarize final repeated trials only after all frozen cases have three eligible B trials and three eligible C trials:

```powershell
.\.venv\Scripts\python.exe -m governance.evaluation final frozen.json trials.json references.json baselines.json
```

`references.json` maps each frozen case ID to its full unchanged reviewed reference. `baselines.json` is an array with one scored A artifact per case. The final command replays scores against those references and includes A, B, and C in the case summaries. It keeps original and human-reviewed B/C results separate, with per-error-type scores, raw-count distributions, proposal/documentation assessments, efficiency statistics, and per-case measurement readiness. Unmeasured original detections, synthetic demo runs, cached replays, missing cache metadata, provider failures, changed hashes, and incomplete case repetitions are excluded from final evidence and remain visible as limitations.

The final JSON checks internal consistency and excludes malformed or duplicate trials. It does not cryptographically authenticate raw measurement files or human identities. Preserve the original artifacts with controlled custody and independently verify the held-out source, reference, and reviewer records before treating a study as externally audited.

## What this repository can and cannot claim

Local automated tests prove validation, read-only boundaries, privacy filtering, bounded execution, review/version state transitions, scoring edge cases, source-key serialization, and evaluation bookkeeping. They do not prove a live MySQL server grant, provider account access, model quality, advisor agreement, or a final performance result. The UI keeps evaluation readiness pending until those external inputs exist.

## Synthetic development fixtures

`evaluation/pilot/` contains eight explicit static checks for the built-in `DemoSource`, a machine-authored draft listing nine expected detections, an unapproved protocol template, and a blank human-review form. They exercise all seven quality metrics; uniqueness flags both rows sharing an email. Non-completeness checks exclude nulls, and the date comparison excludes rows missing either date. The email shape is a development heuristic, not a full email-address validator.

`evaluation/sakila/fault-reference.review-candidate.json` adds the full twelve-column scope, seven candidate rules, eight known injected detections, and clean controls for the public development fault fixture. Accepted meanings and rationales remain null, and `reference_reviewed` is false. It is a review packet, not independent held-out ground truth or a completed human assessment.

Run the fixture contract checks with `.\.venv\Scripts\python.exe -m pytest -q tests/test_evaluation_kit.py`. Matching these predetermined detections checks the implementation only; it is not a model accuracy result or independent evaluation. The development protocol deliberately cannot be frozen. Human approval, review time, source/reference hashes, and acceptance targets remain unset. Use a separate reviewed held-out dataset for final research evidence; these synthetic fixtures are unrelated to the external MySQL dataset integration.
