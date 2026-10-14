# MVP acceptance checklist

Updated 2026-10-14. The required local application flow is implemented. The revised PRD also requires a human-reviewed comparative study; its tools are available, but its measurements remain pending.

| PRD requirement | Implementation and evidence | Status |
|---|---|---|
| Read-only MySQL connection | Restricted connector, validated grants/identifiers, query limits, source-digest comparison | Implemented and tested |
| Schema inventory and declared relationships | Explorer; Sakila with 16 tables, 90 columns, 22 relationships | Implemented and tested |
| Completeness, uniqueness, validity, consistency | Seven allowlisted metrics with explicit eligibility, null handling, and outcomes | Implemented and tested |
| One bounded agent and a fixed workflow | Shared tool contract, enforced budgets, audit, simulated transport tests; successful local Qwen generation/tool/JSON checks | Implemented; local compatibility verified |
| Approve, edit, reject, clarification | Immutable proposal versions, reviewer history, retained originals, explicit check execution | Implemented and tested |
| Rejected rules never execute | Approval filter, stale-version conflicts, integration coverage | Implemented and tested |
| Unsupported tools blocked; exhaustion visible | Allowlist, parameter validation, bounded-loop regression checks | Implemented and tested |
| Inapplicable checks do not fail scores | Eligibility/coverage tests and distinct unavailable/partial outcomes | Implemented and tested |
| Dictionary and quality report | Facts versus proposals, status/evidence/version, approved results, CSV/JSON exports | Implemented and tested |
| Protect model-visible evidence | Shape-only samples, redaction, outbound gate, canary tests, audit/export | Implemented within documented limits |
| Usable local interface | Manual Arabic/English, dark/light, and real Sakila schema review | Verified within reviewed flows |
| Static A, fixed B, adaptive C comparison tools | Frozen A rule file and replayable score, development pilot, frozen B/C trials, row-content identity, runtime contract, cache attestation, and strict trial exclusion | Implemented and tested |
| Original/corrected detection scores | Original detections derived from read-only execution of proposed rules and human mappings; separate corrected results, stable keys, overall/per-error TP/FP/FN, precision/recall/F1 | Tools tested; formal human measurements pending |
| Rule/documentation assessment | Artifact-bound forms, reference coverage, unsupported claims and abstentions | Tools tested; human judgments pending |
| Efficiency and variation | Recorded usage, time, review effort, known-value counts, means and sample deviations | Tools tested; final study pending |
| Held-out cases and frozen targets | Required evidence enforced; unapproved templates cannot count as final | Human preparation/agreement pending |
| Three uncached B/C trials per case | Trial identity, cache/protocol/row-content/reference and repetition validation | Actual final trials pending |
| Findings even without improvement | Undefined metrics remain N/A; incomplete measurements remain pending | Final findings pending |
| Related-work comparison | Current official documentation and primary research reviewed; no claims of head-to-head product performance | Desk review documented; see [related work](related-work.md) |

## Run and verify

`./run.ps1` starts the loopback application. Configure a restricted MySQL source locally and use the existing local Qwen provider for model inspection. No cloud key is required. The optional synthetic demo exercises the workflow without either service.

`./scripts/check.ps1` runs offline verification without a model request; `-LiveMySQL` adds checks against the isolated public-data server when it is available. Current and historical verification evidence is recorded in [status](status.md), with fixture details in [public-data testing](public-data-test.md).

## Remaining final-study inputs

1. Use the development pilot to establish comparable budgets; a full fixed pass over the 90-column Sakila schema needs at least 91 calls plus sufficient time/tokens.
2. Have a human prepare/review reference meanings, business rules, known violations, and independently designed held-out cases.
3. Agree on targets and shared settings, then freeze the reference/protocol before held-out testing.
4. Run three eligible uncached B and C trials per case, assess original proposals, map detections, and measure review time against an appropriate baseline.
5. Generate the final summary and write measured findings and limitations. A source-backed desk review is in [related work](related-work.md); do not imply hands-on product benchmarks.

See the [evaluation protocol](evaluation.md) and [review guide](evaluation-review.md). Production deployment and multi-user authentication are outside the local MVP; local Qwen support is already implemented.
