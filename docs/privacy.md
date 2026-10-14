# Privacy controls in Clarity

The user initially selected Gemini privacy first on 2026-09-28, then asked to
use their local Qwen3-4B-Instruct-2507 model through LM Studio. This extends the
existing source projection and read-only workflow. `hg.md` is a requirements reference;
its sample code, benchmark numbers, and compliance claims are not evidence.

## Implemented controls

1. **Full value redaction.** The model receives schema identifiers, declared
   types/relationships and exact aggregate counts. The sample tool returns only
   type and a coarse text-length bucket (for example `9-16`). Email domains,
   phone suffixes, IDs, card digits, date values, free text, comments, raw samples,
   violation row IDs and database error details are withheld. MySQL calculates
   nullness and length inside the database; sample SQL does not select raw values.
2. **Bounded selection.** Defaults target 5% of the recorded row count, rounded
   up, capped at ten descriptors and at the requested limit. Selection uses a
   local seeded random generator from at most 100 descriptors. Primary keys
   order the MySQL candidate pool when available. This is not a uniform sample
   of the entire population, and tables without a primary key have no guaranteed
   stable candidate order. These samples cannot establish population prevalence.
   Deterministic quality checks still evaluate their full eligible population.
3. **Outbound contract.** Every model request from the inspection loop validates
   the canonical message history before provider submission. Source evidence
   must match the allowlisted projection; raw/unknown fields, malformed JSON,
   unmatched tool results, and selected sensitive literal patterns block the
   request. Errors are generic and omit offending values. Literal detection is
   supplementary, not a complete personal-data detector.
4. **Audit and UI.** The Privacy page and `/api/export/privacy` expose the policy,
   per-run sampling configuration, checked and blocked request counts, and shape
   descriptor submissions. Submissions include history replay/retries, so they
   are not counts of unique source rows. Older runs without an audit are identified
   separately. A run blocked by invalid policy records one blocked attempt with
   zero provider requests.

Set these optional values in `.env.local` and restart:

```dotenv
PRIVACY_SAMPLE_RATE=0.05
PRIVACY_MAX_SAMPLES=10
PRIVACY_SAMPLE_SEED=42
```

The rate must be greater than zero and at most 0.1, the maximum is 1–10, and the
seed is 0–2147483647. Invalid settings block inspection. Redaction cannot be
disabled using these settings. The source is not mutated by masking or sampling.

## Provider handling

Select local Qwen with `LLM_PROVIDER=local`, `LOCAL_MODEL=qwen3-4b-instruct-2507`,
and `LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1`. Start the model's server in
LM Studio first. The adapter uses OpenAI-compatible Chat Completions over HTTP,
accepts only loopback endpoints, disables redirects, and requires no cloud API key.
Local processing keeps model requests on this computer, but the application still
passes schema identifiers and the allowlisted aggregate evidence to the model.
This alone is not a privacy certification; secure the computer, LM Studio logs,
and local reports according to the data owner's rules.

Select Gemini with `LLM_PROVIDER=gemini`. The adapter uses Interactions with
`store=false`, sends its key in an HTTP header, bounds response size, and retains
only opaque thought signatures privately for subsequent tool turns. Signatures
are included in the input budget and excluded from saved reports; they are reset
between runs. See [Google's Interactions reference](https://ai.google.dev/api/interactions-api)
for API semantics. `store=false` controls API interaction storage and is not a
claim about every provider-side log, processing purpose, or retention policy.

`scripts/configure-gemini.ps1` offers a hidden terminal prompt for the key. It saves
plaintext local configuration without making a model request. The project lives
inside OneDrive, so synchronization policy also applies to `.env.local`.

## Decisions on the supplied guide

| Guide item | Implementation decision |
| --- | --- |
| Partial email/phone/ID/card masking | Full value withholding; no retained real character fragments |
| Random 5–10% samples | Seeded, bounded descriptor pool; hard output cap of ten |
| Format-preserving encryption | Not included in this selected phase; no encrypted raw values need to leave the source |
| Local models | Qwen3-4B-Instruct-2507 through LM Studio is supported; Ollama is not configured |
| DEI entropy ratio | Not reported as leakage; the example does not establish disclosure risk |
| k-anonymity | Not claimed: there is no released row-level dataset with reviewed quasi-identifiers |
| Accuracy retention | Unknown until paired, reviewed model experiments are performed |
| Composite risk / compliance badges | Not fabricated; controls do not certify legal compliance |
| Claimed milliseconds / accuracy | Unmeasured examples, not project results |

FPE requires reviewed algorithms, key management and domain constraints. Preserving
a format does not imply preservation of numeric order or all statistics. NIST's
[SP 800-38G revision draft](https://csrc.nist.gov/pubs/sp/800/38/g/r1/2pd) documents
security restrictions for this class of encryption. NIST's
[de-identification guidance](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-188.pdf)
also distinguishes masking from sufficient de-identification.

## Verification and limits

Tests cover seeded reproducibility, output caps, invalid settings, empty and small
populations, exact-length generalization, projection canaries, malformed histories,
and a privacy violation stopping the next provider request. Gemini tests capture
outbound HTTP requests through a local mock transport. Live MySQL tests use only
the separately downloaded public Sakila instance on port 3307 and verify source
hashes remain unchanged.

Schema names and exact aggregate counts may themselves be sensitive. These
controls do not provide differential privacy, anonymity or a zero-risk guarantee.
Only use approved non-sensitive or synthetic test sources with external providers.
Local reports may contain source row IDs from approved checks; the outbound model
filter does not anonymize every application export. Model accuracy and privacy
trade-offs remain unevaluated until real, reviewed trials are available.
