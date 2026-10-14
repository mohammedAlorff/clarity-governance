# Configuration

These settings apply to the local MVP. Keep credentials in `.env.local`; `.env.example` contains the supported names and placeholders. Environment variables already set in the process take precedence over dotenv files.

## Connect MySQL

Copy `.env.example` to `.env.local`, set the `MYSQL_*` entries locally, and restart. Keep the file private. Choose MySQL in the source picker. A restricted MySQL account and an existing test schema are required. The application does not create source schemas or change data.

A database administrator can provision an account for a reviewed test schema with direct `SELECT` grants only. Do not use root/admin credentials. Roles, source-write privileges, stored-routine privileges, file privileges, and grants outside the selected schema are rejected. See `src/governance/source.py` for supported connection settings and enforced limits. SQL is generated exclusively from validated server-owned templates; there is no arbitrary SQL endpoint.

Schema identifiers must contain ASCII letters/digits/underscores, start with a letter or underscore, and be at most 64 characters. The MVP targets small test schemas: metadata is limited to 100 column records and 100 relationship records; larger results fail visibly. Report violation counts remain complete, while at most 100 row identifiers are returned per check. Pattern length is at most 256 characters; the bounded local matcher accepts a restricted token grammar and evaluates values up to 512 characters. Only numeric, text, and date families support applicable range/format/comparison checks; uniqueness is column-level. Completeness treats SQL NULL as missing; blanks remain values. This null policy is recorded in reports.

Set `MYSQL_SSL_CA` to enable verified TLS (certificate and host verification). Optional `MYSQL_SSL_CERT` and `MYSQL_SSL_KEY` support a client certificate. With `MYSQL_ALLOWED_TABLES` configured, the account must have direct grants for those individual tables instead of a schema-wide grant.

## Use local Qwen

The local adapter is configured for Qwen3-4B-Instruct-2507 in LM Studio. Load the model, start its local server on port `1234`, and set these values in `.env.local`:

```dotenv
LLM_PROVIDER=local
LOCAL_MODEL=qwen3-4b-instruct-2507
LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1
```

Restart Clarity after changing settings. The endpoint must use HTTP on a loopback address; remote hosts and URLs with credentials are rejected. No cloud key is required. Inspections still use the privacy filter, request limits, and human review workflow. Local inference speed depends on available hardware.

## Configure cloud models

Choose `LLM_PROVIDER=gemini`, set `GEMINI_MODEL=gemini-3.8-flash`, and enter your Gemini API key locally with `./scripts/configure-gemini.ps1`. Obtain the key from [Google AI Studio](https://aistudio.google.com/api-keys). The hidden terminal prompt saves it to `.env.local`; it is never accepted as a command argument or sent in chat. Restart the app afterward. The key file is plaintext configuration; protect it like the existing MySQL credentials. This workspace is inside OneDrive, so its synchronization settings also apply.

OpenAI remains available by explicitly selecting `LLM_PROVIDER=openai` and setting `OPENAI_API_KEY` and `OPENAI_MODEL`. There is no automatic provider fallback. Pin a model available to your account before evaluation. Cloud providers are optional and their live account compatibility has not been verified for this project. Local Qwen generation, tool calls, and final-proposal JSON were successfully exercised through the adapter; no cloud key is required for that workflow.

**Agent** chooses subsequent inspections using previous results. **Fixed workflow** uses a predetermined inspection sequence with the same tools and configured budgets. Both support Gemini Interactions and OpenAI Responses. The local adapter uses OpenAI-compatible Chat Completions. Provider failures and malformed outputs are bounded and visible. Configure the selected provider's `*_INPUT_PRICE_PER_MILLION` and `*_OUTPUT_PRICE_PER_MILLION` to estimate cost. Gemini output usage includes thought tokens. Missing token/pricing data stays unknown; estimates do not establish actual billing or free-tier eligibility.

Source samples expose types and length buckets, never raw values. Comments, row IDs, credential fields, and error details are withheld from model-visible evidence. See [privacy controls](privacy.md) for the enforced sampling policy, outbound gate, audit report, and limitations. Schema identifiers and exact aggregate counts remain visible. These controls do not establish anonymity, legal compliance, or a measured accuracy-retention rate.

## Checks and reports

Supported checks: completeness, uniqueness, numeric/date range, allowed values, restricted pattern, same-row column comparison, and referential consistency. Every business rule must have a reviewed immutable version. All rows in a duplicate group fail uniqueness. Optional nulls are excluded from uniqueness/validity; comparison nulls are excluded from eligibility. Format/range/uniqueness expectations are proposals until approved.

Rule and dimension scores use eligible row-check cases. Overall score averages dimensions with computed results. Empty, failed, unrun, and inapplicable checks are distinguished; incomplete coverage marks the score Partial. Scores describe only the reported rule set and cannot establish comparative detection accuracy. Exported dictionaries retain draft/rejected/approved status; proposed text is never labeled as an approved fact. A report is a snapshot: if approved rule versions change afterward, it is marked outdated until checks are run again.


## Run budgets

`src/governance/contracts.py` defines `RunLimits`: 40 tool calls, 8 model steps, 60 seconds, 16,000 total tokens, 3,000 output tokens per request, and one retry by default. The bootstrap schema read counts as one tool call. Exhaustion is an explicit result, not a successful full inspection.

The browser starts with these defaults. Open **Inspection limits** to set an explicit budget, then use **Check readiness**. **Start inspection** also checks readiness first. The form retains settings during page navigation within the session; a reload restores defaults. Every new inspection stores its effective limits in the audit, including exhausted or failed runs. Older records show unknown limits.

The local API accepts partial `limits` objects and rejects unknown fields, strings, booleans, nonfinite numbers, and out-of-range values. Its upper bounds are 500 calls, 32 steps, 600 seconds, 200,000 total tokens, 16,000 output tokens per request, and three retries. All fields must be positive except retries, which permits zero. These are request limits, not a promise of completion or a price quote. The Python evaluation protocol can freeze explicit `RunLimits` independently of browser limits.

A fixed workflow profiles each selected column before requesting proposals: the full 90-column Sakila schema needs at least 91 tool calls plus adequate time and token budgets, so it cannot complete under the default 40-call budget. Preflight counts this requirement from the connected schema snapshot, checks local provider and sampling configuration, and sends no model request or source query. It does not verify credentials, account/model access, source freshness, or sufficient time/tokens. Direct API calls may intentionally use a smaller budget and receive `budget_exhausted`.

Use a reviewed, restricted source or an explicit evaluation budget; do not compare runs with different budgets as equivalent. The [development pilot](evaluation.md#development-pilot-before-freezing) supports trying budgets before a final protocol is frozen.
