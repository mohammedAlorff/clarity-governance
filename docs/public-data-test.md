# Public-data MySQL verification

This development test uses **Sakila 1.5 downloaded from Oracle/MySQL**, with a separately downloaded **MySQL Community Server 8.4.11**. It does not use the existing Windows MySQL service, its binaries, accounts, or databases.

## Sources and provenance

- [Official Sakila installation guide](https://dev.mysql.com/doc/sakila/en/sakila-installation.html)
- [Sakila ZIP download](https://downloads.mysql.com/docs/sakila-db.zip)
- [Sakila SQL data license: New BSD](https://dev.mysql.com/doc/sakila/en/sakila-license.html)
- [Official MySQL server downloads](https://dev.mysql.com/downloads/mysql/8.4.html)
- [Portable MySQL 8.4.11 ZIP](https://dev.mysql.com/get/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip)

Sakila is a public sample database for a film rental business. It is explicitly permitted by the revised PRD as development data. Familiar public data is not an independent held-out evaluation.

The downloaded server archive matched the published MD5 `2e833921898a9a030ea6bfe81bd811bc`. Recorded SHA-256 hashes:

| Archive | SHA-256 |
|---|---|
| Sakila | `e27ed871082e76e9d32021c2df07f97ebf7696ace132f5995218557dd87d7046` |
| MySQL | `a492371d687d2bab088b0062581144a0044b8964baefdf4faa579292b423d25c` |

Original SQL files, with their copyright/license headers, are retained under `data/public-mysql/dataset/sakila-db/`. Downloads, runtime binaries, generated credentials, and reports stay under the ignored `data/public-mysql/` folder. Mutable server files are stored at `%LOCALAPPDATA%\Clarity\public-mysql\server-data`, outside the protected/synchronized Desktop directory.

## Verified baseline

The imported database has **16 tables, 90 columns, 22 declared relationships, and 47,268 rows**. All 90 columns were profiled. Seven explicit developer-authored rules exercise completeness, uniqueness, range, allowed values, pattern, column comparison, and referential checks. No violations were found against these seven definitions; this is not a claim that all possible business requirements are satisfied.

The fixture's uppercase-name convention is only a development test rule. It is not a general rule for people's names. Missing return dates are excluded from the date-order check because an open rental may not have been returned yet.

The technical probe hashes every table's contents before and after checking. The hashes matched. The detailed artifact is `data/public-mysql/clean-check-report.json`, with download provenance, schema, counts, seven individual results, and the unchanged-data evidence.

## Known-fault check

A separate `sakila_faults` schema contains 40 rows copied from public Sakila. Seven deliberate mutations produce eight expected rule/row detections because a duplicate pair contributes two violations. The original Sakila schema is not modified. The fixture relaxes selected column constraints so it can represent bad values that the original schema would reject.

The engine found **8 of 8 expected detections**, with **0 extra detections** and **0 missed detections**. All **62 clean rule/row controls** passed. Definitions and the machine-authored injection reference are under `evaluation/sakila/`; the actual detailed result is `data/public-mysql/fault-check-report.json`. These numbers characterize the small technical fixture, not the AI agent's performance.

The clean and known-fault probes were rerun successfully after the provider-module refactor on **2026-09-30**. Fresh verification on **2026-10-14** passed **12 live MySQL integration tests** in 4.99 seconds. Tests cover approval/rejection/edit versions, report/dictionary export, all seven metrics, redacted samples, unchanged source snapshots, the 90-column fixed profiling pass with a simulated provider, and an INSERT permission denial from MySQL (error 1142). The attempted INSERT selects zero rows, so a privilege regression would fail the test without adding data. The suite emitted one upstream Starlette/httpx deprecation warning. No model endpoint was contacted.

## Repeat the checks

Run from the project directory:

```powershell
.\.venv\Scripts\python.exe scripts/public_mysql.py start
.\.venv\Scripts\python.exe scripts/check_public_data.py
.\.venv\Scripts\python.exe -m scripts.public_data_faults verify
$env:GOVERNANCE_LIVE_MYSQL='1'
.\.venv\Scripts\python.exe -m pytest tests/test_mysql_live.py -q
Remove-Item Env:GOVERNANCE_LIVE_MYSQL
```

To stop only this isolated instance while retaining its files:

```powershell
.\.venv\Scripts\python.exe scripts/public_mysql.py stop
```

The script checks the server's data directory before managing it. It binds only `127.0.0.1:3307`, never installs a Windows service, and never uses port 3306. Setup refuses to replace an existing data directory or Sakila schema. The application account has `SELECT` on `sakila.*` only; the bootstrap administrator is used solely for creating the isolated test fixture and managing its process. Passwords are generated locally and omitted from commands/reports.

On a new machine, download the two archives above into `data/public-mysql/downloads/`, verify their hashes, extract Sakila into `data/public-mysql/dataset/` and MySQL into `data/public-mysql/runtime/`, then run `python scripts/public_mysql.py setup` with the project's virtual environment. The Windows server requires its standard Visual C++ runtime dependency.

Create the fault fixture once with `.\.venv\Scripts\python.exe -m scripts.public_data_faults setup`; subsequent runs use `verify`. Repeated setup refuses to replace an existing fixture or account.

## Application and remaining evaluation

The original development workspace's `.env.local` was configured with the isolated Sakila reader. Submission copies exclude that private file; configure a new local read-only connection after setting up the lab. Start the app with `run.ps1`, choose MySQL, and connect to browse the public schema. The seven baseline definitions are in `evaluation/sakila/baseline.json`. Technical test decisions use an automated test reviewer in temporary app storage, separate from real human reviews.

These MySQL fixture checks do not call an AI provider. The project is configured for local Qwen through LM Studio; direct generation, tool calls, and final-proposal JSON have succeeded through its adapter. Model-generated description quality, human-review measurements, acceptance thresholds, and independent final evaluation remain pending. These integration checks do not supply academic performance evidence for the agent. The full 90-column fixture exceeds the default fixed-workflow tool-call budget; see [run budgets](configuration.md#run-budgets) before planning model trials.
