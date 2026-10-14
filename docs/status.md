# Current status

Updated 2026-10-14. Clarity is a local single-user application for read-only MySQL inspection, human review, quality checks, and data-dictionary/report export. Application readiness and the final comparative research study are separate deliverables.

## Application

- `run.ps1` starts the application on `127.0.0.1:8000`. Application code, launch tools, dependencies, tests, and guides are included in the submission package.
- The browser interface supports Arabic/English and dark/light themes. MySQL and adaptive inspection are the initial choices; the synthetic demo is an optional, labeled walkthrough.
- The configured provider is local Qwen, `qwen3-4b-instruct-2507`, through the loopback LM Studio endpoint. Its existing configuration is retained. Opening pages and checking local readiness send no model request.
- Adaptive and fixed workflows share validated tools, privacy filtering, and bounded calls, steps, time, tokens, and retries. Effective limits and outcomes are recorded with each inspection.
- Proposals retain their original output and immutable review versions. Approval, editing, rejection, and clarification are supported. A separate action executes approved checks.
- Seven check types cover completeness, uniqueness, validity, and consistency. Reports distinguish missing, inapplicable, failed, and partial results; dictionaries preserve proposal/review status.
- SQLite stores scopes, proposals, decisions, and run records locally. After restart, the latest MySQL schema, proposals, dictionary, and saved report remain available as a disconnected view. Inspection/check execution requires a connection; connecting creates a new scope and retains earlier records in storage.
- Final-evaluation tools bind trials to a streamed row-content hash, schema, provider/model, code/privacy contract, and frozen budgets. The static A rule file is frozen too, response-cache disabling requires an operator attestation, and the final command replays A/B/C scores from reviewed references. A separate read-only research measurement executes original proposed rules without activating them in the app; original detection scores are derived from those outputs and human mappings.

## Verification evidence

- A manual browser review confirmed Arabic/English switching, dark/light themes, and real Sakila schema rendering: 16 tables, 90 columns, and 22 declared relationships.
- Earlier direct Qwen generation, tool-call, and final-proposal JSON requests succeeded through the project adapter. This establishes local transport compatibility. It does not measure recommendation quality or the final study's results. No new model request is needed for the current application checks.
- Fresh verification on 2026-10-14 passed 289 Python tests, including all 12 isolated live-MySQL integration tests, plus 68 subtests. All 13 frontend behavior tests, Ruff lint/format, Python compilation, and JavaScript syntax checks also passed. One upstream Starlette/httpx deprecation warning was emitted. The live tests confirmed read-only grants, unchanged source snapshots, full 90-column profiling with a simulated provider, and API approval/edit/reject/check/export behavior. The automated suite did not contact a model endpoint.
- Public-data probes verified all 90 Sakila columns and 47,268 rows; the source hashes matched before and after checks. The separate fault fixture produced eight expected detections, no extra or missed detections, and 62 clean controls. These are deterministic engine checks. See [fixture evidence](public-data-test.md).
- Static baseline A was rerun on 2026-10-14 against both development fixtures: seven checks returned zero violations on clean Sakila, and the fault fixture yielded 8 TP, 0 FP, 0 FN with 62 clean controls. The source snapshot remained unchanged. See the [preliminary evaluation report](evaluation-report-draft.md); these runs do not measure B/C or model quality.
- A separate [six-run older-GPT development proxy](../evaluation/codex-pilot/README.md) is complete: three fixed B and three adaptive C Codex-agent runs, each with preserved sanitized evidence, original proposals, action logs, and technical scores. All six produced zero exact-reference detections on the machine-authored fault fixture; C observed six positive aggregate metric probes across its runs, but none became an approved or exact-match rule. This does not complete the app-provider or human-reviewed held-out comparison.
- A complete but **unapproved** twelve-column [reference review candidate](../evaluation/sakila/fault-reference.review-candidate.json) is available for the public fault fixture. Human meanings and rationales are intentionally blank; this fixture is not an independent held-out case.
- The full-Sakila fixed-workflow integration test profiles 90 columns in 91 tool calls with simulated model output. The default 40-call budget is insufficient for that full pass; [explicit limits](configuration.md#run-budgets) and the [development pilot](evaluation.md#development-pilot-before-freezing) support choosing an adequate budget.
- GitHub Actions is configured for offline checks on Windows/Python 3.11 and 3.14. The first hosted run remains pending. Optional cloud-provider account compatibility is not established by the local Qwen checks.

## Final research evaluation

The tools are implemented. A preliminary evidence report is in [evaluation report draft](evaluation-report-draft.md); the PRD's comparative effectiveness evaluation still requires:

1. A development pilot using comparable B/C budgets, followed by human-reviewed references and independently designed held-out cases.
2. Advisor/team agreement on targets and a frozen protocol, including the exact model artifact/provider settings, prompts, tools, row-content snapshots, budgets, and rule definitions.
3. At least three independent uncached fixed-workflow (B) and adaptive-agent (C) trials per final case, with the documented static baseline (A).
4. Read-only execution of original rule proposals, human judgments on proposals and documentation, mappings to the frozen reference, corrected detections, and recorded review effort. A reduced-effort claim also needs a comparable measured baseline task.
5. A final report of accuracy, coverage, variation, time, usage/cost, limitations, and any unsuccessful outcomes. A documentation-based related-work review is now available in [related work](related-work.md); hands-on competitor benchmarks are not claimed.

Use the [acceptance checklist](acceptance.md), [evaluation protocol](evaluation.md), and [human review guide](evaluation-review.md). Synthetic fixtures and public-schema checks cannot substitute for those measurements.

The SHA-256 hashes and score replay detect inconsistent or accidentally edited files; they do not authenticate who created a raw measurement. Formal study operators must preserve original artifacts with controlled custody and independently verify the source, reference, and reviewer records. The current engineering checks cannot replace that research oversight.

## Supported scope

This is a loopback, single-user application. Production authentication, multi-user operation, and deployment hardening are outside this release. Privacy controls do not establish anonymity, legal compliance, or measured accuracy retention. The revised PRD is preserved as the requirements baseline; its description of local model support as a future option has been superseded by the implemented adapter.
