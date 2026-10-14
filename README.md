# Clarity — Autonomous Data Governance Engine

A local application for read-only MySQL inspection, human-reviewed governance proposals, quality checks, and a data dictionary. The primary workflow uses MySQL and the optional local Qwen model; a synthetic demo is available without either service.

[Architecture](docs/architecture.md) · [Configuration](docs/configuration.md) · [Development](docs/development.md) · [Contributing](docs/CONTRIBUTING.md) · [GitHub upload](docs/github-upload.md) · [Changelog](docs/CHANGELOG.md)

[Security policy](SECURITY.md)

Released under the [MIT License](LICENSE).

## Start

Requires Python 3.11+; verified locally with Python 3.14. Run from this project folder:

```powershell
.\run.ps1
```

On first launch, the script creates `.venv`, installs the pinned dependencies, and installs the app from `src`. Open [Clarity Studio](http://127.0.0.1:8000). The redesigned interface opens in Arabic and dark mode, with English and light-mode toggles. This is a local single-user MVP; keep the server on loopback.

## Folder structure

```text
GP/
├── src/
│   └── governance/           # Python application
│       ├── providers/       # Local Qwen, Gemini, and OpenAI adapters
│       ├── static/          # Browser HTML, CSS, and JavaScript
│       └── ...              # API, agent, quality, privacy, storage
├── tests/                   # Unit, API, and integration tests
├── scripts/                 # Setup, checks, credentials, public-data tools
├── requirements/            # Dependency ranges, lock, development tools
├── docs/                    # Architecture, guides, status, research protocol
├── evaluation/              # Baseline definitions and evaluation fixtures
├── .github/                 # CI workflow, issue forms, and pull-request template
├── pyproject.toml           # Package and Python tool configuration
├── run.ps1                  # Start the application
├── SECURITY.md              # Vulnerability reporting guidance
└── README.md
```

Private `.env.local`, `.venv`, caches, generated package metadata, and `data/` stay local and are ignored by Git. Copy `.env.example` only when configuring a provider or MySQL source.

### Use local Qwen with LM Studio

Load `qwen3-4b-instruct-2507` in LM Studio, start its local server on port 1234, then set `LLM_PROVIDER=local`, `LOCAL_MODEL=qwen3-4b-instruct-2507`, and `LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1` in `.env.local`. Restart Clarity. The local adapter accepts loopback URLs only and does not require a cloud API key. LM Studio may stay off until you explicitly start an inspection. The model gets the same filtered schema and aggregate evidence described in [Privacy](docs/privacy.md).

## Try the workflow

1. Prepare a restricted MySQL test source and configure its read-only account in `.env.local`; see the [public Sakila setup](docs/public-data-test.md).
2. Connect **MySQL** in Clarity. Schema browsing and deterministic checks do not require a model request.
3. With the configured Qwen server running, select **Adaptive agent** → **Start inspection**. Review **Inspection limits** first; **Check readiness** checks local configuration without contacting the model.
4. Review evidence and assumptions; approve, edit, reject, or request clarification.
5. Select **Run approved checks**. Approval alone does not execute a rule. View and export the **Quality report**, **Data dictionary**, and **Privacy** report.

The **Synthetic demo** remains optional for a deterministic walkthrough without MySQL or a model. Demo results are labeled and never presented as live agent output.

## Put the project on GitHub

This folder is the standalone project root. Follow the [GitHub upload guide](docs/github-upload.md) to create a repository and push it. The included ignore rules exclude local credentials, databases, generated files, and virtual environments.

Reviews and immutable versions are stored in `data/governance.db`. After restart, the latest MySQL schema, proposals, dictionary, and saved report remain viewable with the source marked disconnected. Reconnect before a new inspection or check run; connecting creates a new scope and preserves earlier records.

## Development

```powershell
.\scripts\setup.ps1 -Dev
.\scripts\check.ps1
```

Node.js is needed for JavaScript syntax and frontend behavior checks. GitHub Actions is configured to run the same offline checks on Windows with Python 3.11 and 3.14 after upload; a remote run is still pending.

## Documentation

- [دليل التسليم والتشغيل بالعربية](docs/handover.md): ترتيب GP وخطوات التشغيل الفعلي والإعداد.
- [GitHub upload guide](docs/github-upload.md): create a clean repository and push this project.
- [Configuration](docs/configuration.md): credentials, connection settings, and budgets.
- [Architecture](docs/architecture.md): module responsibilities and data flow.
- [Privacy](docs/privacy.md): outbound controls and their limitations.
- [API](docs/api.md): routes, review transitions, and exports.
- [Public MySQL verification](docs/public-data-test.md): isolated Sakila test data.
- [Evaluation](docs/evaluation.md): references, frozen targets, and independent trials.
- [Human evaluation guide](docs/evaluation-review.md): blank review forms, assessment criteria, and measured outputs.
- [MVP acceptance checklist](docs/acceptance.md): requirement coverage and remaining external inputs.
- [Current status](docs/status.md): verified results and remaining work.
- [Related work](docs/related-work.md): source-backed review of research and documented alternatives.
- [Evaluation report draft](docs/evaluation-report-draft.md): verified engineering evidence and the remaining comparative-study requirements.
- [Older-GPT development comparison](evaluation/codex-pilot/README.md): six blinded Codex proxy runs on the isolated public-data fixture, with original proposals and technical scores; this is separate from the formal held-out study.
- [Revised PRD](docs/PRD-autonomous-data-governance-engine-revised.md): requirements.

Local Qwen generation, tool calls, and final-proposal JSON have been verified through the project adapter. Qwen was left off for the current comparison; the separate Codex proxy used older GPT agents without an OpenAI API key. The final human-reviewed comparative study remains pending; application checks and development fixtures do not establish model accuracy or reduced review effort. Historical planning notes are preserved under [docs/archive](docs/archive/README.md).
