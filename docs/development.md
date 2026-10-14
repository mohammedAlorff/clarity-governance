# Development

Run all setup and checks through `scripts/`. Python 3.11+ and Node.js are required.

```powershell
.\scripts\setup.ps1 -Dev
.\scripts\check.ps1
```

Setup creates the project's `.venv`, installs pinned dependencies, and installs `src/governance` in editable mode. Code changes take effect without reinstalling. The launchers resolve the project directory from their own location, so they can also be invoked by absolute path from another directory.

## Dependencies and package layout

| File | Purpose |
|---|---|
| `requirements/base.txt` | Runtime dependency ranges used by package metadata |
| `requirements/lock.txt` | Tested, pinned environment and build backend |
| `requirements/dev.txt` | Locked environment plus Ruff |
| `pyproject.toml` | Editable package definition, static assets, pytest, and Ruff settings |

This application is run from its source checkout using editable installation. Configuration and local data remain at the project root; a standalone wheel deployment is not a supported runtime configuration.

## Checks

`scripts/check.ps1` checks Python lint/imports, formatting, compilation, JavaScript syntax, dependency-free frontend behavior tests, and the complete offline pytest suite. It stops on a failed stage and restores the caller's directory and live-MySQL environment setting. It does not install packages or call a model. Live MySQL tests are disabled unless explicitly selected:

```powershell
.\.venv\Scripts\python.exe scripts/public_mysql.py start
.\scripts\check.ps1 -LiveMySQL
```

This uses only the already-provisioned public fixture at `127.0.0.1:3307`. The tests verify its port, data directory, schema, and reader identity. See [fixture setup](public-data-test.md) before using the option on another machine.

To format a change:

```powershell
.\.venv\Scripts\python.exe -m ruff check src scripts tests --fix
.\.venv\Scripts\python.exe -m ruff format src scripts tests
```

Python uses four spaces, single-quoted strings, and a 100-character formatting target. The browser files are served directly from `src/governance/static/`; no frontend build tool is required.

## Git and CI

The `GP` delivery folder has a local `main` branch with the project files staged and no commit or remote. Follow the [GitHub upload guide](github-upload.md) to set your Git author name and email, create the first commit, and push it. Local secrets, databases, caches, runtimes, and package build outputs are ignored; these rules do not control cloud synchronization.

The [GitHub Actions workflow](../.github/workflows/checks.yml) runs the same setup/check scripts on Windows with Python 3.11 and 3.14, using pinned actions and read-only permissions. It needs no provider key or MySQL server. The first hosted run remains pending. See [GitHub's Python CI documentation](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).

## Boundaries and evidence

Follow the [contribution guide](CONTRIBUTING.md) and [architecture](architecture.md). Keep SQL restrictions in `source.py`, eligibility/scoring in `quality.py`, and provider transport details in `providers/`.

`tests/test_architecture.py` checks provider independence and application/static-asset discovery from another working directory. Transport tests simulate provider replies; they do not establish live account compatibility. A known upstream Starlette/httpx test-client warning is reported rather than suppressed. See [current results](status.md).
