> Historical record from the initial build. This is not current operating guidance; see [current status](../status.md) and [architecture](../architecture.md).

# Autonomous Data Governance Engine: GP1 design

The user approved building the working MVP from revised PRD v1.1 and explicitly requested building now with provider credentials configured later. The supplied revised PRD is the requirements brief; the older workspace PRD is historical context.

## Outcome and boundaries

A local browser application supports connect, inspect, propose, review, explicitly run approved checks, and export a dictionary/report. Source MySQL is read-only. SQLite contains application state only. One bounded adaptive model loop and a predetermined model workflow share inspection tools. A synthetic deterministic demonstration is clearly labeled and is never counted as a live model or independent evaluation trial.

GP1 includes all four quality dimensions where applicable, immutable proposal versions, review audit history, separated proposed/approved descriptions, scoring and coverage, and evaluation utilities. Real provider trials, MySQL integration, human reference review, and advisor-approved frozen thresholds need external inputs; software and local tests cannot establish those results.

## Selected approach

Python FastAPI serves a static HTML/CSS/JavaScript interface and JSON endpoints. Python is shared by metrics, MySQL access, and evaluation, while SQLite provides transactional review storage. This is smaller than a separate React frontend and separate worker deployment, and offers more direct control of validation than a notebook-only prototype. The app binds to loopback and is a single-user test tool, not a production deployment.

## Module interfaces

- `governance/source.py`: `DemoSource()` and `MySQLSource.from_env()` expose `get_schema()`, `run_metric(metric_id, target, parameters)`, `sample_column(table, column, limit)`, and `close()`.
- Schema is `{name, tables: [{name, row_count, columns: [{name, data_type, nullable, key}]}], relationships: [...]}`. Targets are `{table, column}`. Relationships are declared facts.
- `governance/quality.py`: `validate_rule(rule, schema)` validates an executable `{metric_id, target, parameters}`; `summarize_results(results)` scores completed eligible checks and preserves all statuses and coverage.
- Metric IDs: `profile`, `completeness`, `uniqueness`, `range`, `allowed_values`, `pattern`, `column_compare`, `referential`. `profile` is inspection only. Result shape: `{metric_id, target, dimension, status, eligible, passing, violations, reason, violation_ids}`. Status strings: `completed`, `not_applicable`, `not_run`, `failed`, `no_eligible_data`.
- `governance/agent.py`: `RunLimits`, `OpenAIClient`, and `run_inspection(source, client=None, mode='demo', limits=None)` return `{status, proposals, trace, usage, provider, model, elapsed_seconds}`. Proposals have `kind` (`rule`/`description`), `target`, `title`, `description`, `evidence` (list of strings), `assumptions` (list), `status` (`draft`/`needs_clarification`), and `rule` or null.
- `governance/store.py`: transactional SQLite proposal versions, review events, inspection records, and reports. Edits supersede the old version with a new draft. Rejected/superseded versions cannot activate. Approving stores reviewer and timestamp but does not execute checks.
- `governance/app.py`: API orchestration, source selection, dictionary and reports, exception normalization, and same-origin mutation checks.
- `governance/evaluation.py`: deduplicated detection metrics, trial summaries, and freeze validation. Final evaluation rejects missing human-reviewed reference/targets and uncached repeat requirements.

## Safety and failure behavior

MySQL access uses permitted identifiers and server-owned parameterized SELECT templates, read-only transactions, server timeouts, and bounded outputs. The app never executes model SQL. Defaults withhold raw samples and comments; the model sees aggregate counts and shape representations. Provider errors are generic; trace contains validated calls and bounded summaries. Credentials remain in local environment files and are not serialized. Canary tests cover outbound prompts and trace.

Tool calls, model steps, wall time, and token usage are bounded. Responses and tool arguments are validated. Insufficient evidence produces a clarification proposal. Provider absence is visible and does not silently invoke a different provider. The synthetic demo remains available without external dependencies.

## UI and outputs

Workspace overview, schema explorer, review queue with evidence and version history, data dictionary, quality report, and evaluation readiness are reachable through a sidebar. A warm off-white canvas, dark forest navigation, restrained green/orange status colors, and clear typography prioritize review. Every action has pending/error/empty feedback. JSON report and CSV dictionary exports preserve statuses and provenance.

## Verification

Tests cover rejected-rule exclusion, edit/approval version boundaries, unsupported calls, privacy canaries, budgets, duplicate-group semantics, empty/failed/inapplicable score cases, coverage, and deduplicated precision/recall. HTTP tests exercise the complete demo flow and persistence. Browser verification covers review/edit/run/export and narrow layouts. Live integrations are documented as unverified until credentials and a MySQL test instance are supplied.
