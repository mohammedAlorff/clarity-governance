# Contributing to Clarity

Start with the [README](../README.md) and [architecture](architecture.md). Keep changes focused on one behavior or responsibility so they can be reviewed independently.

## Set up and check a change

1. Create a branch from the current project baseline.
2. Run `scripts/setup.ps1 -Dev` to install dependencies and the application; see [development setup](development.md).
3. Add or update a focused test when changing behavior. Use synthetic fixtures and simulated provider responses.
4. Run `scripts/check.ps1`. Use `-LiveMySQL` only with the isolated public-data fixture described in [MySQL verification](public-data-test.md).
5. Update documentation when configuration, behavior, or module boundaries change.
6. Summarize the problem, solution, and verification in the pull request.

## Review expectations

- Preserve explicit human approval before checks execute and immutable review history.
- Keep source queries read-only and generated from validated templates.
- Preserve the privacy gate and bounded model/tool budgets when modifying inspection or provider code.
- Distinguish synthetic results, engine tests, and actual model-evaluation evidence.
- Keep `.env.local`, credentials, databases, downloaded runtimes, and generated reports outside Git. `.env.example` contains placeholders only.

GitHub Actions runs the same offline check command on Windows with Python 3.11 and 3.14 when the repository is hosted on GitHub. It does not need model keys or a MySQL server. A local passing check does not establish a successful remote CI run.

For a bug report, include the expected behavior, reproduction steps using synthetic/public data, Python version, and sanitized error message. Do not paste secrets or private source records into an issue.
