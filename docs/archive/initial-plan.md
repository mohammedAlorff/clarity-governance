> Historical record from the initial build. This is not current operating guidance; see [current status](../status.md) and [architecture](../architecture.md).

# Governance MVP Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement these tasks. Track evidence below.

**Goal:** Build the local working GP1 application described by revised PRD v1.1.

**Architecture:** FastAPI serves the review interface; SQLite persists immutable proposals and reports. Read-only sources feed validated deterministic metrics and a bounded provider-isolated inspection loop.

**Tech Stack:** Python, FastAPI, SQLite, PyMySQL, HTTPX, plain JavaScript/CSS.

**Spec:** `docs/archive/initial-design.md`, together with the user-supplied revised PRD.

## Global constraints

- Source data remains read-only; only application storage is written.
- Business rules execute only after review, through a separate run action.
- Original proposals and reviewer/version provenance remain available.
- Synthetic demo results cannot be presented as real model evaluation.
- User selected implementation now, credentials configured later.
- No production deployment, provider requests, or held-out-result claims in this build.

## Review focus

- Edits to approved/rejected proposals cannot carry approval forward.
- Empty, failed, and inapplicable checks cannot produce fabricated passing scores.
- Database text, raw values, and provider errors cannot bypass outbound filtering.
- Malformed model output or repeated calls must terminate within limits.
- Changing source cannot execute rules belonging to another inspection scope.

## Task 1: Sources and quality engine

Files: `governance/source.py`, `governance/quality.py`, `tests/test_quality.py`, `tests/test_source.py`.
Interfaces: implement the source/quality contracts in the spec. Include synthetic fixture rows and fixed baseline configurations for local demonstration, plus environment-driven MySQL.

- [ ] Write and run failing tests for duplicate-group failures, null/empty populations, applicability, target validation, and score coverage.
- [ ] Implement validated metrics and source adapters with explicit time/output limits.
- [ ] Run `python -m pytest tests/test_quality.py tests/test_source.py -q`; all must pass.

## Task 2: Agent and evaluation

Files: `governance/agent.py`, `governance/privacy.py`, `governance/evaluation.py`, corresponding tests, evaluation protocol documents.
Interfaces: consume source methods; emit proposal/trace/usage shape specified in design. Use model API only when configured; no network in tests.

- [ ] Write failing tests for unsupported tools, limits, outbound canaries, structured-response rejection, and detection deduplication/zero denominators.
- [ ] Implement a provider adapter, fixed/adaptive workflows, synthetic demo workflow, filtering, and reproducible evaluation helpers.
- [ ] Run relevant tests and verify no live provider calls occur.

## Task 3: Persistence and HTTP application

Files: `governance/store.py`, `governance/app.py`, `tests/test_store.py`, `tests/test_app.py`, setup/start scripts.
Interfaces: stores own proposal ID/version/review status; exposes API described in `docs/api.md` for UI. Runtime uses one selected source and scope-bound proposals.

- [ ] Write failing tests proving edits create drafts, rejected versions stay rejected, and approvals do not execute.
- [ ] Implement transactional storage, app routes, validated review payloads, report export, and connection configuration.
- [ ] Exercise complete demo connect/inspect/review/run/report with FastAPI TestClient and persistence reload.

## Task 4: Browser interface

Files: `governance/static/index.html`, `governance/static/styles.css`, `governance/static/app.js`.
Interfaces: API in `docs/api.md`; escape all database/model text; no HTML interpolation of untrusted content.

- [ ] Build responsive schema, proposal review, dictionary, report, and evaluation views.
- [ ] Verify approve/edit/reject/clarify actions, empty and error states, and explicit run checks.
- [ ] Inspect browser rendering and narrow viewport behavior.

## Task 5: Integration and handoff

Files: `README.md`, `.env.example`, `docs/evaluation.md`, test reports.

- [ ] Run complete test suite and compile/import checks.
- [ ] Request independent code review of privacy, execution gating, scoring, and normal user flow; resolve material findings.
- [ ] Start local app and open browser preview; record concrete checks and limitations.
- [ ] Deliver run instructions and distinguish working software from pending live evaluation.
