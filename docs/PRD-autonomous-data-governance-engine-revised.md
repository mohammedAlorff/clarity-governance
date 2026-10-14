# Product Requirements Document
## Autonomous Data Governance Engine

**Working title:** Autonomous Data Governance Engine  
**Scope description:** AI-assisted MySQL data quality and documentation  
**Version:** 1.1  
**Status:** Revised draft for discussion  
**Last updated:** 2026-09-26

## Executive Summary

The system helps a database owner understand a poorly documented MySQL database, identify data quality issues, and prepare a reviewable data dictionary. SQL/Python computes the metrics. One LLM agent uses schema information and approved profiling results to propose descriptions and quality rules.

The agent can choose its next inspection step, but a person reviews proposed rules before they are used as quality requirements. The system reads the source database and reports findings; it does not repair or modify source data.

The project supports a limited part of data governance. It does not provide a complete governance program or independently establish business policies. Its main evaluation question is: **Does agent-assisted inspection improve useful recommendations or reduce review effort compared with simpler approaches?** The answer must come from testing, not from the project title.

## 1. Problem and Motivation

Poor documentation and unclear names can make databases difficult to understand. For example, `C_PH` might refer to a phone number, but the name alone does not establish its meaning or the correct validation rule.

The system combines schema, relationships, locally calculated statistics, and safe sample representations to suggest an interpretation with supporting evidence. When this information is insufficient, it reports **Needs clarification** instead of inventing a meaning.

Existing products are relevant alternatives. This project does not assume that they lack automatic classification, documentation, or rule suggestions. Any comparison must identify the product version, edition, supported feature, and source used to verify it.

## 2. Goals and Acceptance Criteria

The MVP must:

- Connect to a selected MySQL test database with restricted read access.
- Produce a schema inventory, applicable quality checks, a reviewable data dictionary, and a simple report.
- Use one bounded agent that can select inspection tools based on previous results.
- Support **Approve**, **Edit**, and **Reject** for proposals, plus **Needs clarification** when evidence is insufficient.
- Keep source data unchanged and prevent unapproved proposed rules from becoming active quality requirements.
- Complete the evaluation in Section 7 and report results even if the agent does not outperform the baseline.

Functional acceptance includes demonstrating that a rejected rule is not executed, an inapplicable check is not scored as a failure, an unsupported tool request is blocked, and the agent stops at its configured limits.

Performance targets for detection accuracy, recommendation quality, and review time will be set after a development-only pilot. The team and advisor must record and freeze these targets, the rule definitions, and the evaluation procedure **before running the held-out final test**. Targets must not be chosen to fit the final results.

## 3. Users and Stakeholders

- **Database owner or analyst:** Reviews descriptions and proposed rules, then examines findings.
- **Project team:** Builds the system and prepares reproducible experiments.
- **Advisor and committee:** Assess the implementation, evaluation, and stated limitations.

The MVP uses test databases. Production deployment is outside the project scope.

## 4. Scope

### GP1 MVP

- MySQL schema profiler.
- SQL/Python quality engine with applicable checks from four dimensions.
- One agent for inspection, documentation, and column-level rule proposals.
- A minimal review screen with proposal status and supporting evidence.
- A data dictionary and simple quality report.
- A fixed baseline and the evaluation described in Section 7.

The MVP covers the complete flow: connect, inspect, propose, review, check, and report. It does not require a large dashboard.

### GP2 Optional Extensions

After the MVP and evaluation are complete, the team may add report history, a dashboard, or suggestions involving multiple related tables. For example, a reviewer could approve a proposed relationship check between an order and its customer.

These extensions can use the same agent. Additional agents, PostgreSQL support, and a local model adapter are future options, not required deliverables.

### Out of Scope

- Automatic data repair, source-schema changes, or database administration.
- A complete governance platform, compliance certification, or autonomous business-policy approval.
- Training a model or maintaining custom model-hosting infrastructure.
- Production databases containing real sensitive records during testing or demonstrations.
- n8n orchestration and a custom interactive relationship editor. If a relationship diagram is included, use Mermaid.

## 5. System Architecture

The system has a MySQL connector, a deterministic metrics engine, one agent, a review interface, and a report generator. A small `LLMClient` interface isolates the selected model provider. Supporting another provider later still requires compatibility testing.

The agent uses these typed inspection tools:

| Tool | Purpose |
|---|---|
| `get_schema()` | Returns permitted tables, columns, types, keys, and declared relationships. |
| `run_metric(metric_id, target, parameters)` | Executes an allowlisted metric using a server-owned SQL template and validated inputs. |
| `sample_column(table, column, limit)` | Returns a bounded representation that passes the server's privacy filter. It may return no samples. |

The LLM does not submit arbitrary SQL. Identifiers must match the permitted schema; metric parameters must pass validation. Basic profiling metrics are approved system capabilities. A newly proposed business rule is a draft until a reviewer approves its validated configuration.

The decision loop is: inspect available evidence, select an allowed tool, inspect the result, then propose a description or rule, request clarification, or stop. Each run has configured limits for tool calls, time, and token use. Store tool names, validated inputs, result summaries, and concise decision reasons for review.

All writes, including proposal status and reports, go to separate application storage. The source database remains read-only.

## 6. Functional Requirements

### Schema and Profiling

Read the selected schema and declared relationships. Profile only permitted targets. Keep observed facts, such as column types, separate from inferred meanings. A declared relationship and an agent-suggested relationship must be labelled differently.

### Quality Checks

Support completeness, uniqueness, validity, and consistency where they apply. Each check records its target, dimension, parameters, eligible population, null handling, and rule version.

Uniqueness is appropriate only when the field or key is expected to be unique. Repeated city names are not an error. A proposed format or range is not a business requirement until it is approved.

After approval, applying a rule means running a read-only check and reporting violations. It never means changing values. Results distinguish **Completed**, **Not applicable**, **Not run**, **Failed to run**, and **No eligible data**.

### Proposals and Review

Each description or rule includes the target, proposed meaning, evidence, assumptions, and status. Rules also identify the metric and configuration that would execute them.

- **Approve:** Accepts the current validated proposal version.
- **Edit:** Creates an updated draft that must pass validation and be approved before use.
- **Reject:** Stores the decision and prevents that proposal version from being activated.
- **Needs clarification:** Records missing information without inventing a description or rule.

Record the reviewer, timestamp, and approved version. A separate explicit run action executes approved rules. Keep original model proposals available so evaluation can distinguish model output from human corrections.

A numerical LLM confidence score is not required for the MVP. If added later, label it as an uncalibrated model estimate unless evaluation supports a stronger interpretation. Evidence and review status remain visible.

### Outputs

The data dictionary contains schema facts, proposed or approved descriptions, evidence, and review status. The report contains rule results, counts of violations, applicable quality dimensions, coverage, unresolved items, and model/run identifiers. Draft descriptions must not appear as approved facts.

## 7. Benchmarking Methodology

### Reference Data and Test Separation

Use Sakila or Northwind for development, and include an independently designed small schema for held-out testing. A public schema may already be familiar to a model; its public availability does not establish an independent evaluation.

Before the final test, prepare a human-reviewed reference containing accepted column meanings, confirmed business rules, and known violations. Original column names can inform this reference, but are not sufficient ground truth for detailed descriptions or rules.

Create cases with meaningful names and cases with obscured names. For fully obscured cases, use neutral labels such as `T01` and `C01`; document which relationships, types, and other clues remain visible. Include cases where the available evidence cannot identify a unique meaning.

Synthetic data and injected errors are valid test methods. Keep a manifest of confirmed violations and include clean data to measure false alarms. Separate development cases from final test cases, and keep reference answers and error locations hidden from the agent. Do not tune the system on the final test and then report it as untouched evidence.

### Three Comparisons

| Variant | Behavior |
|---|---|
| A — Static rules | Runs a fixed, documented rules baseline without an LLM. |
| B — Fixed LLM workflow | Uses the selected LLM with a predetermined inspection sequence. |
| C — Agent | Uses the same LLM and tools, choosing subsequent inspections from observed results. |

Give B and C access to the same information sources and the same maximum tool/token budgets. Record actual usage. Use the same database snapshots and task cases across all variants. Apply the same review procedure to proposals and record human edits separately.

### Measurements

- **Violation detection:** Define a detection unit as a reference rule ID and stable row ID, adding a column or target identifier where needed. Map equivalent proposed rules to the reference definition and deduplicate alerts. TP is a true violation detected, FP is an incorrect alert, and FN is a known violation missed. Report Precision = TP / (TP + FP), Recall = TP / (TP + FN), and F1, by error type and overall. Report raw counts; zero-denominator metrics are N/A, not automatic success.
- **Rule proposals:** A reviewer assesses the original proposals against the reference for correctness, applicability, and usefulness. Report correct proposals, incorrect proposals, and coverage of reference rules. User approval alone is not proof of correctness.
- **Documentation:** Assess factual correctness and unsupported claims against the human reference, accepting equivalent wording. Report abstentions and the share of columns receiving a supported description.
- **Efficiency:** Measure model cost, elapsed system time, tool calls, and human review time. Any claim of reduced human effort must include a measured manual or baseline task under comparable conditions.

Report original agent performance and the result after human review separately. Freeze model/version, prompts, settings, tool definitions, snapshots, and test cases before evaluation. Run B and C at least three times per final case with response caching disabled, and report variation as well as averages. Cached replay may support a demo, but does not count as an independent trial.

## 8. Quality Scores and Coverage

Quality scores describe performance against a stated set of rules. They do not certify that all possible data problems have been found.

| Dimension | Eligible population and pass condition |
|---|---|
| Completeness | Required values under an approved rule; pass when present. Define whether blanks count as missing. |
| Uniqueness | Non-null values or key tuples that are expected to be unique; every row in a duplicate group fails. Required nulls are handled by completeness. |
| Validity | Eligible non-null values; pass when they satisfy the approved pattern, set, or range. |
| Consistency | Eligible rows or relationships; pass when an approved cross-field or referential rule holds. Define treatment of missing related values. |

For each completed rule with a nonzero eligible population:

```text
Rule score = passing cases / evaluated eligible cases
Dimension score = sum of passing cases / sum of evaluated eligible cases
```

The dimension formula pools row-rule cases: one row tested by two rules contributes two cases. Report each rule separately as well, so this weighting is visible.

Let D be the dimensions with valid computed results. With nonnegative dimension weights and a positive denominator:

```text
Overall quality score = 100 × sum(w[d] × dimension_score[d], d in D)
                              / sum(w[d], d in D)
```

Use equal dimension weights for the initial baseline. Document and freeze any alternative weights before final testing. The formula renormalizes over dimensions with results; missing results must still be visible through coverage and status.

```text
Check coverage = completed applicable checks with nonzero eligible populations
                 / all approved applicable checks in the evaluation scope
```

**Not applicable** checks are excluded with a reason. **Not run**, **Failed to run**, and **No eligible data** checks stay visible and reduce coverage when they belong to the approved applicable scope; they never receive a passing score. If no valid results exist, the score is **Unavailable**. If coverage is incomplete, label the score **Partial**. If no checks apply, coverage is N/A.

Also report selected versus profiled columns. Coverage is relative to the declared inspection scope, not a claim that every possible issue was checked. Do not compare overall scores from different rule sets as evidence that one system is more accurate; use the shared reference and detection metrics in Section 7.

## 9. Privacy and Access Controls

Use synthetic or reviewed non-sensitive test data for the MVP. Apply the outbound privacy filter to all model-visible tool results, including schema comments, samples, metric outputs, and error messages. Raw sensitive values and connection credentials must not reach the external model or prompt logs.

The application, not the agent, decides what to mask or withhold. Masking does not automatically guarantee anonymity and may remove evidence needed for interpretation; request clarification when the remaining evidence is insufficient.

Use a database account restricted to the selected schema and required read operations, with no source-write, file-access, or stored-routine execution privileges. Enforce query timeouts, output-size limits, and agent-run limits in code. Treat database text as data, never as instructions that can change tool permissions.

Store credentials outside prompts and reports. Use canary values in tests to verify that prohibited content is absent from outbound requests and logs. Local model support may be explored later; it does not replace access controls or review requirements.

## 10. LLM Requirements and Reproducibility

Use one off-the-shelf model supporting tool calls and structured responses. Validate every response before use, and handle malformed output or provider failures with bounded retries and a visible status.

Record the provider, model/version, supported settings, prompts, and actual usage. A low temperature, where supported, does not guarantee identical outputs. Repeated runs and recorded inputs provide evidence of stability.

Cache may reduce development and demo costs, but disable response caching for independent evaluation trials. Measure costs during the pilot rather than assuming they are small. A second provider or model is optional and requires separate validation.

## 11. Contribution and Alternatives

The proposed contribution is an evaluated workflow for inspecting poorly documented MySQL schemas, presenting evidence-backed descriptions and rule proposals, and supporting human review.

Great Expectations, Soda, and OpenMetadata are candidates for a related-work comparison. Document the verified capabilities, version/edition, configuration effort, and fit for the selected task. Do not mark a competitor's capability as absent without checking it. Benchmark metrics evaluate this project; they are not themselves a unique product capability.

The project can succeed as applied engineering even if a simpler workflow performs as well as the agent. Report that result and prefer the simpler implementation when appropriate.

## 12. Main Risks and Mitigations

| Risk | Response |
|---|---|
| Incorrect descriptions or business rules | Show evidence and assumptions; support clarification, review, and rejection. |
| Evaluation leakage | Separate development and held-out cases; hide reference answers; freeze the evaluation. |
| Misleading quality scores | Define populations and applicability; report rule results, coverage, and partial status. |
| Unsupported differentiation claims | Verify alternatives and present contribution as a testable hypothesis. |
| Excessive agent cost or looping | Enforce tool/time/token limits and measure usage. |
| Sensitive data exposure or unsafe tool requests | Filter all model-visible outputs and enforce permissions and allowlists in code. |
| Scope expansion | Deliver one agent and MySQL first; keep extensions optional. |

## 13. Roadmap

1. Define a small test schema, human reference, and fixed rules baseline.
2. Implement the read-only connector and deterministic checks.
3. Add proposals, review states, and a data dictionary/report.
4. Add the single-agent loop and the fixed LLM workflow for comparison.
5. Run a development pilot, agree on acceptance thresholds, then freeze and run the final evaluation.
6. Add GP2 features only if the required flow, functional checks, and evaluation are complete.

## 14. Committee Discussion

**What did the team build?**  
The connector, validated inspection tools, rule engine, bounded agent loop, review workflow, documentation/report generation, and evaluation suite. The model is an external component.

**Why use an agent?**  
Adaptive inspection may help when schema meanings are unclear. The fixed-workflow comparison tests whether this flexibility actually improves results or efficiency.

**Why not use an existing product?**  
The team will compare relevant capabilities and setup requirements. The contribution is the implemented and evaluated workflow, not an unsupported claim that alternatives cannot perform similar tasks.

**Does the system prevent hallucinations?**  
It reduces their impact through evidence, clarification, human review, and validation. It cannot promise to eliminate them.

**Does it modify the database?**  
No. It runs permitted read-only inspections and checks. Approved proposals and findings are stored separately.

**How is success measured?**  
Detection accuracy, correctness and coverage of original proposals and documentation, review effort, runtime, and cost on held-out cases. The final report includes limitations and unsuccessful results.

## 15. Design References

- [DAMA — What is Data Management](https://dama.org/about-dama/what-is-data-management/): context for the broader scope of data governance.
- [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents): workflows, agents, and the value of starting with a simple design.
- [Claude documentation — Glossary](https://platform.claude.com/docs/en/about-claude/glossary): temperature and nondeterministic API outputs.

These references inform the design. They are not evidence that the proposed system has already achieved its performance goals.
