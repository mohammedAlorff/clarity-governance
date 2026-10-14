> Historical record from the initial build. This is not current operating guidance; see [current status](../status.md) and [architecture](../architecture.md).

# Build progress — governance MVP

User confirmed: working MVP; build now and configure credentials later.

Ruling: Use the supplied revised PRD as the approved brief and proceed on the user's explicit “Build now” instruction. Design and plan document implementation decisions without adding another permission cycle.

Ruling: This workspace is not a Git repository and contains no application. Build directly in the user-selected folder; do not create a separate checkout or fabricate commit history.

Initial ruling: No project MySQL or model credentials were configured. Build live adapters plus an explicitly synthetic demo and contract tests.

Preflight: Source/quality, agent/evaluation, storage/API, and static UI share only the interfaces in the design and docs/api.md. File ownership is disjoint; root owns integration.

## Public-data verification continuation

User directed internet dataset testing and explicitly excluded the installed MySQL/data. Downloaded official Sakila 1.5 and a separate portable MySQL 8.4.11, verified the archive checksum, and initialized only an isolated loopback instance on port 3307. No connection to the existing Windows MySQL service was made.

Ruling: Use Sakila as development data, as already specified in the PRD. Kaggle was an example, not a required provider; Oracle's original downloadable MySQL fixture is directly compatible and licensed. This does not replace the independently designed held-out case.

Ruling: Windows denied the new server writes under the protected Desktop. Keep mutable server files under LOCALAPPDATA/Clarity/public-mysql, with project scripts, downloads, and reports under this workspace. No access-control settings were changed.

Verified: 16 tables, 90 profiled columns, 22 declared relationships, 47,268 rows. Seven baseline checks completed; full-content hashes matched before/after. Application /api/connect successfully selected the downloaded Sakila through a SELECT-only reader. OpenAI model configuration remains absent and no provider calls were made.

Verified known-fault copy: 40 public rows in a separate sakila_faults schema; seven injected mutations produced eight expected detections, zero false positives/misses, and 62 passing clean controls. Full suite with live MySQL enabled: 95 passed, 26 subtests passed, one upstream deprecation warning. Python compile and JavaScript syntax checks passed. Independent review found no material issue in isolation, grants, or evidence labeling. Public-data testing is complete; model credentials and final human-reviewed research evaluation remain pending.
