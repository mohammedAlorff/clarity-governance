# Put Clarity on GitHub

This guide assumes the `GP` folder is the repository root and you want to publish it to a new GitHub repository. The local repository is initialized on `main`; its project files are staged, and it has no commit or remote yet. The ZIP archive intentionally omits `.git` history.

## Before publishing

Review the [current project status](status.md) and decide whether the repository should be public or private. This project uses the [MIT License](../LICENSE), which permits reuse, modification, and distribution subject to its notice and warranty terms. Keep the license file in the repository.

The `.gitignore` excludes `.env.local`, credentials, local databases, downloaded data, build outputs, and Python environments. Keep `.env.example` as the shareable configuration template. Never commit real MySQL credentials, API keys, research data, or private provider logs.

## Create the repository

On GitHub, create an empty repository. Do not initialize it with another README, `.gitignore`, or license; those files are already managed in this folder. Open PowerShell in `GP`, set the author identity you want recorded in Git, then commit and push:

```powershell
git config user.name "YOUR NAME"
git config user.email "YOUR EMAIL"
git status --short
git commit -m "Initial Clarity project"
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Replace the example remote address with the one GitHub shows for your repository. Inspect the staged file list before committing. Do not add `.env.local`, `data/`, `.venv/`, or private evaluation records.

After the push, open the repository's **Actions** page. The Windows workflow runs the offline checks on Python 3.11 and 3.14; the first hosted run is the final check that GitHub accepts the repository and workflow configuration.

## Project readiness

The application, tests, documentation, public-data fixtures, evaluation tools, and GitHub Actions workflow are included. The formal comparative study remains pending human approval of its reference and independent provider trials. Read [evaluation status](evaluation-report-draft.md) before presenting development results as model-quality evidence.
