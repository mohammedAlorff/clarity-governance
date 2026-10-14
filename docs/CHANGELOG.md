# Changelog

This file records notable project changes. Entries under Unreleased are local development work, not published releases.

## Unreleased

### Added

- Local Qwen adapter for a loopback LM Studio server, with successful generation, tool-call, and final-proposal JSON compatibility checks.
- Arabic/English interface with dark/light themes, source and model status, and a five-stage governance workflow.
- Submission packaging with a SHA-256 manifest, excluding local credentials and runtime data.
- Restored MySQL schema, proposals, dictionary, and report views after restart without automatically reconnecting to the source.
- Human evaluation forms bound to original trial artifacts, rule/documentation assessment metrics, per-error-type detection scores, and efficiency summaries with unknown values preserved.
- Final measurement readiness checks for complete human assessments and recorded review time in each frozen B/C case.
- Frozen A rule-file hashes, read-only baseline scoring, source-row and schema fingerprints, runtime-contract checks, cache-disable attestation, and replayable A/B/C final scores. Malformed, duplicate, cached, and score-inconsistent trials are excluded from final evidence.
- Configurable inspection limits, local readiness checks, and persisted limits in the inspection audit.
- A development-only pilot command with a no-model-request readiness option and explicit exclusion from final evaluation.
- Dependency-free frontend behavior tests for readiness and inspection controls.
- Local governance workflow: source connection, inspection, versioned human review, approved quality checks, and dictionary/report exports.
- Gemini and OpenAI adapters, bounded inspection modes, and explicit provider selection.
- Privacy controls for model-visible evidence, descriptor sampling, and outbound request auditing.
- Isolated public Sakila test fixtures and evaluation protocol templates.
- A shared verification command and a GitHub Actions workflow for offline checks.

### Changed

- Grouped application sources under `src/`, dependency files under `requirements/`, launch/check tools under `scripts/`, and contributor documents under `docs/`.
- Added editable application installation so imports and static assets resolve outside the project directory.

- Separated provider transports from inspection orchestration and shared contracts.
- Applied consistent Python formatting and import conventions.
- Reorganized current documentation and preserved initial planning notes in an archive.

### Pending verification

- Human-reviewed research evaluation and optional cloud-provider account compatibility.
- First GitHub-hosted workflow run after the repository is uploaded.
