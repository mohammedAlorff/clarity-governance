# Related work and documented alternatives

Reviewed 2026-10-14 from the linked primary papers and official product documentation. This is a documentation-based comparison, not a hands-on benchmark of the products. Capabilities and editions can change; recheck them if the study protocol is frozen later.

## Existing data quality tools

| System | Capabilities verified in official documentation | Relationship to Clarity |
|---|---|---|
| Great Expectations (GX Core 1.24 documentation) | Expectations encode verifiable assertions; suites group them for validation. The documentation includes uniqueness, schema, and integrity workflows, including custom SQL for some cross-table checks. | Covers declarative validation and results. Clarity's point of comparison is the proposal-and-review workflow around schema exploration, alongside a fixed and adaptive inspection comparison. GX should be tested directly before making claims about effort or relative coverage. |
| Soda Core v3 / Soda platform | Soda Core v3 is documented as an open-source library/CLI using SodaCL. Official documentation describes user-defined checks, dataset discovery, column profiling, and platform capabilities for anomaly monitoring and contracts; some profiling and platform features depend on the chosen edition/deployment. | Covers profiling and rule execution, with platform/edition-specific monitoring. The comparison should identify the exact version and deployment; Clarity does not claim to replace production observability. |
| OpenMetadata 1.10 documentation | Supports table- and column-level quality tests, technical and business-oriented tests, no-code test setup in its UI, and viewing test results by table or suite. | Covers catalog, test authoring, and quality-result visualization. A fair comparison must account for its broader metadata platform and setup scope. |

These products already provide substantial quality checks and governance workflows. The project must not claim that they lack data profiling, validation, review, or monitoring. A defensible contribution is narrower: implement and evaluate a read-only MySQL workflow that compares static rules (A), fixed inspection (B), and adaptive inspection (C) under shared evidence and budgets, with original proposals and human-corrected results measured separately.

## Research context

LLMDap explores using LLMs and retrieval-augmented generation for automatic metadata enrichment and dataset discoverability. It supports the relevance of semantic metadata generation, but does not establish that Clarity's proposed rules or descriptions are accurate.

DiscoveryBench formalizes multi-step, data-driven discovery and reports evaluations over 264 research-derived tasks plus 903 synthetic tasks. Its authors report that the best evaluated system scored 25% on that benchmark. The result is specific to DiscoveryBench and must not be transferred to Clarity; the methodological lesson is to break down agent work into verifiable stages and test it on held-out tasks.

## Evaluation implications for this project

- Existing deterministic tools are credible baselines. The project's static A baseline and common detection keys are necessary to test whether LLM-guided workflows add value.
- Keep database permissions read-only, proposed rules separate from execution, and review decisions separate from correctness judgments.
- Use independently designed held-out data, hide its reference from the model, freeze source hashes and budgets, and run repeated uncached B/C trials before interpreting accuracy or cost.
- Report agent output and human-corrected output separately. A simulated provider or analyst-authored output can verify plumbing, but cannot be reported as a run by Qwen or as model-quality evidence.
- Treat this document as a desk review. No competitor was installed or run, so no comparative performance or setup-time claims are made.

## Sources

- [Great Expectations, Create an Expectation](https://docs.greatexpectations.io/docs/core/define_expectations/create_an_expectation/), and [GX data integrity use cases](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/integrity/).
- [Soda Core v3 overview](https://docs.soda.io/soda-documentation/soda-v3/overview-main), [SodaCL metrics and checks](https://docs.soda.io/soda-documentation/soda-v3/sodacl-reference/metrics-and-checks), and [Soda profiling](https://docs.soda.io/soda-documentation/soda-v3/soda-cl-overview/profile).
- [OpenMetadata 1.10: No-Code Test Cases](https://docs.open-metadata.org/v1.10.x/how-to-guides/data-quality-observability/quality/test).
- [Jiang et al., LLMDap: LLM-based Data Profiling and Sharing, VLDB 2025 workshop paper](https://www.vldb.org/2025/Workshops/VLDB-Workshops-2025/DEC/DEC25_5.pdf).
- [Majumder et al., DiscoveryBench, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/0d70af566e69f1dfb687791ecf955e28-Abstract-Conference.html).
