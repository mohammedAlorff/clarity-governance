# Local API contract

All APIs use JSON. Error responses expose `detail` with a safe message. POST requests require `Content-Type: application/json`. App is single-user on loopback.

- `GET /api/state`: `{source: {mode, name, connected}, schema: object|null, proposals: [...], inspections: [...], report: object|null, settings: {provider, model_configured, model, configuration_error}, privacy: {policy, runs, checked_requests, blocked_requests, legacy_runs_without_audit, accuracy_retention, compliance_certified, limitations}, evaluation: {status, message}, counts: {tables, columns, pending, approved}}`.
- `GET /api/export/privacy`: Download the current scope's privacy policy and audit counters as JSON; this is not a compliance or accuracy certification.
- `POST /api/connect` with `{mode: 'demo'|'mysql'}`: select synthetic source or environment-configured MySQL; return state. Connecting creates a fresh inspection scope; older reviews/reports are retained in storage but not active in another scope.
- `POST /api/inspect/preflight` with `{mode: 'demo'|'agent'|'fixed', limits?: {...}}`: check connection state, cached schema, local provider configuration, sampling policy, and full-pass call requirements without querying the source or calling a model. Returns `ready`, `issues: [{code, message}]`, `columns`, `profile_calls_required`, effective `limits`, `provider`, `model`, `sampling`, and `provider_verified: false`. A restored disconnected MySQL scope reports `source_disconnected`. Readiness is advisory; it cannot establish account access, current source state, or adequate time/tokens.
- `POST /api/inspect` with the same body: run inspection and persist its proposals and effective `limits`; return state. Omitted budget fields use defaults. Direct API runs may deliberately exhaust a small budget; the browser checks preflight before starting. See [budget defaults and API bounds](configuration.md#run-budgets).
- `POST /api/proposals/{id}/review` with `{action: 'approve'|'reject'|'clarify', reviewer: string, note: string}`: transition current version; return state. `action: 'edit'` also takes `changes: {title, description, evidence, assumptions, rule}`; unchanged fields may be omitted. Edits create a new draft; `rule` has `{metric_id, target: {table, column}, parameters}` and is validated by `src/governance/quality.py`. Description proposals use `rule: null`. Validation errors are HTTP 422; stale or terminal versions are HTTP 409.
- `POST /api/checks/run` with `{}`: execute only current approved rule versions, return state with new report.
- `GET /api/dictionary`: `{source, columns: [{table, column, data_type, nullable, key, description, status, evidence, version}]}`.
- `GET /api/export/dictionary`: downloadable CSV.
- `GET /api/export/report`: downloadable JSON report, 404 before checks run.
- `GET /api/health`: `{status: 'ok'}`.

After restart, the latest MySQL scope is restored without a source connection: `source.connected` is false, while cached schema/proposals and saved dictionary/report exports remain available. Inspection and check execution require a connection. Connecting creates a new scope; it does not resume the prior scope for live execution.

Each stored proposal exposes `id`, `lineage_id`, `version`, `kind`, `target`, `title`, `description`, `evidence`, `assumptions`, `status`, `rule`, `reviewer`, `reviewed_at`, `created_at`, `original`, `history`, `current`.

Review requests may include `review_seconds` (0–86400), measured from opening a proposal to submitting a decision. This measures interaction elapsed time, not independently measured human effort or a manual-task baseline.

Reports expose `id`, `created_at`, `source`, `results`, `summary`, `unresolved`, `inspection_ids`, `selected_columns`, `profiled_columns`. Summary exposes `overall_score` (0–100 or null), `status` ('complete'|'partial'|'unavailable'), `coverage` (0–1 or null), `dimensions` keyed by dimension, `completed_checks`, `applicable_checks`. Results include `title`, `proposal_id`, `version`, `metric_id`, `target`, `dimension`, `status`, `eligible`, `passing`, `violations`, and `violation_ids`; failed or inapplicable checks also give a safe reason.

Reports returned by state/export also expose `outdated`, computed against currently approved rule versions. `profiled_columns` counts the union of known profiled targets across the scope. Each rule result includes `eligible_population` and `null_handling` strings.
