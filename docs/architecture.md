# Architecture

Clarity is one Python application with a browser interface. The API coordinates the inspection, review, and execution flow; provider adapters translate requests and responses without owning business decisions.

## Responsibilities

| Module | Owns |
|---|---|
| `app.py` | Local HTTP boundary, source selection, request validation, and route orchestration |
| `contracts.py` | Shared run limits, tool/response JSON schemas, and generic provider error |
| `agent.py` | Adaptive/fixed/demo inspection, budgets, validated tool dispatch, and proposal validation |
| `readiness.py` | Local configuration and schema-snapshot preflight without source or model calls |
| `evaluation_review.py` | Blank review forms, human-judgment validation, proposal/documentation coverage, and detection breakdowns |
| `providers/__init__.py` | Explicit provider selection and configuration presence checks |
| `providers/gemini.py` | Gemini Interactions transport and private continuation metadata |
| `providers/openai.py` | OpenAI Responses transport |
| `providers/local.py` | Loopback-only OpenAI-compatible Chat Completions transport for local Qwen |
| `privacy.py` | Model-visible allowlist projection and privacy audit reports |
| `privacy_contract.py` | Outbound message validation before provider calls |
| `sampling.py` | Bounded descriptor sampling and generalized length buckets |
| `source.py` | Synthetic and read-only MySQL sources, validated query templates, and grant checks |
| `snapshot.py` | Bounded streaming row-content fingerprints for frozen research sources; raw values are not written to artifacts |
| `quality.py` | Rule validation, metric definitions, eligibility, and score aggregation |
| `store.py` | SQLite scopes, immutable proposal versions, review history, and run records |
| `evaluation.py` | Protocol freezing, source/runtime provenance, original-rule research measurement, comparison artifacts, and evaluation CLI |
| `static/` | Navigation, review forms, schema/dictionary/report views, and privacy display |

All paths above are relative to `src/governance/`. Provider modules depend on shared contracts, not on the agent, HTTP app, or persistence. An import-isolation test enforces this boundary.

## Inspection and review flow

1. The API connects a source and creates a scope. MySQL validates its selected schema and reader grants.
2. The agent reads the schema and gathers permitted evidence within its budget.
3. Projection removes values and excluded fields; the outbound gate validates the complete model-visible history before each request.
4. The selected adapter sends the request and returns a common response shape. The agent validates tools, proposals, and usage.
5. The API stores proposals as drafts or clarification requests. Human decisions are versioned by the store.
6. A separate explicit action executes approved rule versions against the source. Reports identify the exact versions used.

A provider implements `respond(messages, tools, max_tokens, timeout)`, returning `calls`, `proposals`, `usage`, and `model`. The agent owns retries and budgets. Gemini additionally reports an input-size bound that includes private signatures. A provider constructor never makes a network request.

## Boundaries that must remain intact

- Database content and model replies are untrusted. Models cannot execute arbitrary SQL, approve proposals, or write to the source.
- All providers use the same proposal and tool schemas. Provider wire formats stay inside their adapters.
- Raw sample values, source comments, row identifiers, credentials, and detailed source errors are excluded from model requests. Schema identifiers and exact aggregate counts remain visible.
- Editing creates a new draft. Approval does not execute a check. Changing the source creates a new scope.
- Scores summarize the executed rules and eligibility policy. Synthetic data and injected faults do not establish model accuracy.
- Provider selection is explicit. A failed provider is never silently replaced by another provider or by the synthetic demo.

## Design limits

This remains a small local application: request coordination uses one process-local lock, the browser is plain JavaScript, and storage is SQLite. Authentication, multi-user concurrency, distributed jobs, and production deployment are outside the current implementation. Split modules when responsibility or testability requires it, rather than adding layers solely to increase the folder count.

See [API](api.md), [configuration](configuration.md), [privacy](privacy.md), and [status](status.md) for operational details. [Archived initial design](archive/initial-design.md) records earlier decisions; this page describes the current structure.
