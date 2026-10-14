# Codex development proxy for the A/B/C comparison

**Status:** exploratory development evidence. This is not the formal held-out,
human-reviewed comparison described in `docs/evaluation.md`.

## Why this run exists

The owner requested an older GPT model instead of restarting local Qwen, then
declined creation of an OpenAI API key. Six fresh Codex task agents therefore
use `gpt-5.6-sol` outside the application's provider adapter. Their outputs
must never be attributed to Qwen or represented as in-application B/C trials.

## Source and isolation

The input is a separate MySQL 8 development instance on `127.0.0.1:3307`,
populated from the public MySQL Sakila sample. The small `sakila_faults`
schema contains 40 rows across four tables and seven deliberately injected
changes. A machine-authored reference lists eight rule/row detections and 62
clean rule/row controls. The reference is **not human-reviewed**. The static A
rules were written around these injections, so A is only a rule-engine sanity
check, not an unbiased competitor.

`scripts.study_tool` verifies the isolated server, reader account, fixture
digest, and schema shape before every request. It exposes sanitized metadata,
aggregate counts, or redacted sample shapes; it hides raw values, row IDs,
credentials, and source errors. Each action is logged and counts toward a
20-action limit. The database reader has SELECT-only privileges. The fixture
digest is checked before and after the pilot.

## Recorded trial protocol

Three independent B agents and three independent C agents start with no
inherited conversation history. All use `gpt-5.6-sol`, the same allowed proposal
schema, the same sanitized projection, and development split. They are told
not to inspect source code, baselines, references, fixture construction, other
runs, external sources, or direct SQL. Database identifiers are treated as
untrusted metadata. They may use schema/profile evidence but may not invent
business meanings, requiredness, accepted values, or thresholds. Uncertain
policies must be marked `needs_clarification`; a finding is a proposal for a
human, not an approved rule or confirmed row-level detection.

- **B fixed:** one schema action followed by profiles for all 12 columns in
  schema order (13 total actions), then a final JSON proposal artifact.
- **C adaptive:** one schema action, then up to 19 additional guarded actions
  across at most seven adaptive decision rounds. It can request profiles,
  quality metrics, or redacted shape samples before final JSON.

The 20-action ceiling is enforced and logged by the CLI. The seven-round
ceiling was part of the agent prompt but is not independently instrumented;
only source actions are attested by the saved log. Model selection is recorded
from the organizer's Codex agent invocation and repeated in the artifacts;
those self-declared artifact fields are not an external billing attestation.

Each proposal has `kind`, `{table,column}` target, title, description, evidence,
assumptions, status, and `rule`. Descriptions use `rule:null`. Executable rules
use only these parameter shapes: `completeness:{}`;
`uniqueness:{}`; `range:{min?,max?}`; `allowed_values:{values:[...]}`;
`pattern:{pattern:...}`; `column_compare:{other_column,operator}`; or
`referential:{reference_table,reference_column}`. Unknown policy with no valid
configuration is a clarification description. The original artifacts are
preserved without post-score edits.

The earlier `*_proxy_*` runs were **calibration only**: their prompt named
metrics but omitted the exact parameter contract, resulting in structurally
invalid rules. They are excluded from the recorded comparison. The six
`*_contract_*` runs use the contract above; the agent prompts contain no
reference rule or fault examples. This prompt correction was informed by
calibration output, so this remains development work rather than a preregistered
held-out study.

## Technical scoring and its limits

`scripts.study_score` validates each unedited proposal and, for draft rules
with valid configurations, runs the existing metric engine read-only on the
isolated fixture. It maps a proposal to a reference ID **only when its
configuration exactly equals** a machine-authored baseline rule. It then
compares deduplicated `(rule_id,row_id,target)` detections to the eight reference
entries. Clarification requests are not executed. This strict mapping can miss
semantically useful alternative rules, and an unmatched detection is only
"extra relative to this narrow reference", not proof of a real false alarm.
No proposal is approved or activated in Clarity.

`scripts.study_archive` checks run provenance, counts source actions, computes
per-run and mean/sample-SD summaries, and saves the sanitized evidence,
original proposals, action logs, technical scores, and SHA-256 digests beside
`summary.json`. It verifies both the fixture-row digest and the sanitized
schema digest across all six runs. A C metric probe reporting violations is
only evidence the agent inspected an aggregate anomaly; it is not a matched,
human-approved detection. Token use, cache status, provider cost, comparable model-only
latency, independent held-out performance, human proposal quality, and review
time cannot be established by this proxy. Three runs on one familiar tiny
fixture do not support statistical significance or a general superiority claim.

## Observed results

| Workflow | Runs | Calls/run | Mean proposals (sample SD) | Invalid proposals | Strict reference detections/run |
|---|---:|---:|---:|---:|---:|
| B fixed | 3 | 13 | 15.7 (0.6) | 0 | 0/8 |
| C adaptive | 3 | 20 | 16.7 (1.5) | 0 | 0/8 |

Across the three C runs, six aggregate metric probes reported positive
violation counts; those observations did not become exact-reference draft
rules. Each B/C
run has strict TP=0, FP=0, FN=8, recall=0%; precision and F1 are undefined
because there are no predicted detections. The deterministic A sanity check
has eight matching detections because its seven rules were authored from the
injection design. The [report](../../docs/evaluation-report-draft.md) explains
the limits of these figures, and [summary.json](summary.json) contains the
per-run data and artifact hashes.
