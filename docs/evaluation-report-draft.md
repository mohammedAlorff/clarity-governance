# Evaluation report draft

**Status: six-run development proxy completed; formal comparative study still pending.** This report separates verified application and rule-engine behavior from a small Codex-agent probe. It does not attribute Codex, analyst-authored, or simulated outputs to Qwen.

## Research question

Does Clarity's adaptive, human-reviewed MySQL inspection workflow (C) improve data-quality detection or useful documentation over a fixed inspection workflow (B) and a static rules baseline (A), under comparable evidence, permissions, and resource budgets?

The current evidence does not answer this formal effectiveness question. It establishes that the application and deterministic checks work on development sources, records what an older GPT model proposed under two inspection workflows, and shows which review and held-out measurements are still absent.

## System and safety conditions

Clarity connects to MySQL through a restricted read-only account. It stores proposed rules separately and executes checks only after an explicit approval action. The local provider is configured as Qwen 3 4B Instruct 2507 through a loopback endpoint. During the verification recorded here, the local model was left off; provider preflight made no request. No OpenAI API key was created. The separate proxy used six Codex task agents with `gpt-5.6-sol`, outside Clarity's provider adapter.

The protocol documentation defines A/B/C variants, frozen source and reference hashes, common budgets, at least three uncached B and C trials per held-out case, artifact provenance, human assessment of original proposals, separate corrected results, and measured review effort. These requirements are not satisfied by the engineering checks below.

## Verified preliminary results

| Evidence | Result | What it supports |
|---|---|---|
| Application checks on 2026-10-14 | 289 Python tests passed, including 12 isolated live-MySQL tests; 68 subtests passed; 13 frontend behavior tests passed. Ruff, formatting, Python compilation, and JavaScript syntax checks passed. One upstream Starlette/httpx deprecation warning remains. | Software behavior, bounded calls, read-only access, review transitions, exports, privacy filtering, and evaluation bookkeeping. |
| Public Sakila schema | 16 tables, 90 columns, and 22 declared relationships. The live test confirmed the source snapshot remained unchanged. | Connector and schema inventory on this public development source. |
| Static baseline A on clean Sakila, rerun 2026-10-14 | Seven developer-authored checks completed with zero violations across 47,268 rows; all 90 columns were profiled and the source hash was unchanged. | The static rules did not flag issues on this public development snapshot. The rules are not human-approved business ground truth. |
| Static baseline A on the separate injected-fault fixture, rerun 2026-10-14 | Eight expected rule/row detections, zero extra detections, zero missed detections, and 62 clean controls. | The configured deterministic rules on this small machine-authored fixture. This is not an AI-agent result or independent held-out evidence. |
| Codex development proxy on the injected-fault fixture, 2026-10-14 | Three independent fixed B runs and three adaptive C runs, with original proposals, sanitized action logs, scores, and SHA-256 manifest in [`evaluation/codex-pilot`](../evaluation/codex-pilot/README.md). | Limited proposal behavior under the development fixture and a strict reference-configuration scorer. This is not a formal app-provider comparison. |
| Submission package | The `GP` folder and `GP.zip` include source, tests, documentation, and development evidence; private settings, databases, and runtime files are excluded. Manifest hashes and ZIP entries are verified after each final build. | Delivery integrity for the application and the development-pilot record. |

The clean and injected-fault baseline results characterize these explicit development rules and fixtures. They must not be generalized to unknown business rules, model proposals, or production quality. The clean public schema and its public availability also do not make it an independent held-out case.

## Six-run older-GPT development proxy

An initial set of calibration runs was excluded after its prompt omitted the exact metric-parameter contract. The six recorded `*_contract_*` runs used fresh no-history Codex task agents with the same corrected proposal contract. B received schema plus all 12 profiles in a fixed 13-action sequence; C started with schema and adaptively used the guarded 20-action cap. Both saw only the privacy-filtered projection. No raw values or violation row IDs were supplied to the agents, and no proposed rule was approved in Clarity. The fixture has 40 rows, no declared foreign keys, and a schema name that hints at injected faults; it is not held out.

| Approach | Runs | Mean proposals (sample SD) | Source actions per run | Invalid proposals | Exact-reference detections per run | Technical recall |
|---|---:|---:|---:|---:|---:|---:|
| A: developer-authored static rules | 1 | Not applicable | 8 engine calls including schema | Not applicable | 8 of 8 | 100% on the authored fixture |
| B: fixed older GPT proxy | 3 | 15.7 (0.6) | 13 | 0 | 0 of 8 | 0% |
| C: adaptive older GPT proxy | 3 | 16.7 (1.5) | 20 | 0 | 0 of 8 | 0% |

Each B/C run produced eight valid draft rules, mostly checks based on declared primary keys, and clarification requests for unsupported business policies. C's metric probes returned a positive aggregate violation count six times across three runs, but those probes were **not** approved detections or exact-match draft rules. All B/C runs had 0 true-positive, 0 extra, and 8 missed entries under the narrow exact-configuration reference. Precision and F1 are undefined because none of the executed draft rules produced a detection. Technical recall here measures agreement with seven machine-authored configurations, not general anomaly detection or useful policy coverage. A's rules encode the known injections; its 8/8 cannot be read as an unbiased advantage over B/C. No B-versus-C superiority is supported.

The proxy prompt required models to abstain when schema and aggregate counts could not establish requiredness, accepted values, bounds, or relationships. Strict matching also gives no credit to a useful alternative configuration. The logged 20-action ceiling was enforced; the seven adaptive-decision-round instruction was not independently instrumented. Token use, cache status, cost, comparable model-only time, human correctness judgments, documentation accuracy, and review effort remain unknown. The full [protocol, original artifacts, and summary](../evaluation/codex-pilot/README.md) are packaged for inspection.

## Application-provider model evidence

The project records prior direct Qwen adapter smoke checks for generation, tool calls, and final-proposal JSON. Those checks establish transport/format compatibility only. They are not comparative trial artifacts and do not establish proposal accuracy, documentation quality, repeatability, or cost.

No eligible, completed, uncached **application-provider** B/C trial artifacts with a frozen human-reviewed reference were available for this report. Prior incomplete inspection records and the Codex proxy are not counted as formal trials. Formal precision, recall, F1, proposal correctness, description coverage, review time, and B-versus-C variation therefore remain **unmeasured**. No conclusion that the application agent improves data governance is supported yet. The formal harness checks selected row content before and after each run, freezes the static A rules and a nonsecret code/privacy contract, requires an operator cache-disable attestation, and derives original detection rows from separately executed original proposals. The final scorer replays A/B/C scores against reviewed references. These controls detect internal inconsistency but do not authenticate raw artifacts or replace human reference approval and real provider trials.

## Related work

The project's desk review is in [related work](related-work.md). Official documentation shows that Great Expectations provides declarative expectations and validation, Soda provides checks and profiling with edition-specific platform features, and OpenMetadata provides table/column quality tests and result views. Published work such as LLMDap studies LLM-assisted metadata enrichment, while DiscoveryBench demonstrates the need for structured, held-out evaluation of multi-step data-driven tasks. These sources motivate the study; they are not comparative results for Clarity.

## Steps required for a final study

1. Have the project team or advisor review and approve independently designed held-out cases, the complete reference meanings/rules/violations, acceptance targets, and the frozen protocol.
2. Select budgets after a development pilot. The 90-column fixed Sakila pass requires 91 profiling calls in the simulated-provider integration test, so the default 40-call budget cannot complete that full pass.
3. Run A, B, and C on the same held-out snapshots and information scope. Run at least three independent uncached B and C trials per case and keep the original artifacts.
4. Have reviewers assess original proposals and descriptions, map original and corrected detections to the frozen reference, and record comparable review time.
5. Generate the final repeated-trial summary and report per-error-type results, raw counts, uncertainty/variation, coverage, cost, elapsed time, unsuccessful trials, and limitations. Keep agent output and corrected output separate.

Until these steps are complete, label this as a preliminary engineering evaluation rather than a final effectiveness study.
