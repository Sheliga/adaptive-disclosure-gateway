# Advisor-facing demo application

## Status and purpose

This document defines the **parallel demonstration/application track** for the Adaptive Disclosure Gateway.

It does **not** change Milestone 3 scientific ordering, gates or closure criteria.

The current Python implementation is the **reference application/core** used by the demo. The web application exposes this implementation; it must not recreate simplified B0–B4 logic in Next.js.

The intended audience is a prospective advisor or technical reviewer who may understand AI/software but **does not know this project's vocabulary, treatments, policy matrix, runner or audit schema**.

The UX must therefore explain the concept while the reviewer uses it.

Tracking:

- Demo Track: Issue #41
- T20 application/HTTP boundary: Issue #28
- T21 guided Next.js UI: Issue #29
- T12 normalized document ingestion: Issue #9
- T22 real provider: Issue #30
- T25 container/deploy infrastructure: Issue #42

## Architectural boundary

```text
browser
  ↓
Next.js
  ↓
HTTP API
  ↓
shared Python application boundary
  ↓
disclosure treatment / policy / task analysis
  ↓
provider boundary
  ↓
local authorized reconstruction
  ↓
safe result / metrics
```

The web layer must not independently implement detection, B3 task analysis, B4 policy resolution, disclosure transformations, reconstruction or scientific scoring semantics.

## UX strategy

### Default language

- **Português (Brasil)** is the default locale.
- English is available through an explicit language control.
- User preference should persist.
- Scientific/internal identifiers remain stable; only presentation copy is localized.

### Light and dark themes

Both themes are required from the MVP.

- initial theme follows system preference;
- explicit user override is supported and persisted;
- semantic tokens are shared across themes;
- both themes must meet accessible contrast requirements;
- color is never the only indicator of disclosure action/state.

### Novice-first progressive disclosure

The interface uses three information layers:

1. **plain language** — what stayed local, what was sent, what was removed/substituted/generalized;
2. **explanation** — why the system made each decision;
3. **technical/research details** — B0–B4, policy version/matrix cell, exposure, conformance, utility, audit, timings/resources and provider metadata.

Technical details are available through actions such as `Ver detalhes técnicos`; they do not dominate the default workflow.

## No agents in the first demo

The first demo uses the deterministic/versioned mechanisms already implemented by the research prototype:

- detector;
- B3 task analyzer/action spaces;
- B4 contextual policy mechanism;
- explicit disclosure actions;
- local vault/reconstruction;
- provider boundary.

Agentic variants may be studied later as separately versioned extensions.

## MVP v2 experience

### 1. Boas-vindas / Como funciona

The first screen explains the concept in three short steps:

1. **Análise local** — the document is inspected before anything leaves the trusted environment.
2. **Divulgação controlada** — only the allowed/transformed representation is sent to the external provider.
3. **Reconstrução local** — authorized pseudonyms can be reconstructed after inference.

Primary CTA: **`Testar agora`**.

An optional **`Como funciona a pesquisa?`** path can explain B0–B4 and the experiment design.

### 2. Novo teste

The reviewer chooses one of three entry modes:

- **Usar um exemplo**;
- **Enviar meu arquivo** (drag-and-drop / file picker);
- **Colar texto**.

Then the reviewer states in natural language what the model should do with the content.

The default experience uses the recommended policy-governed strategy. Treatment/provider selection belongs under advanced controls; a new user should not need to know B0–B4 to execute a test.

### 3. Revisão antes do envio

Before the provider call, the application explains:

- what was detected;
- what stays local;
- what is removed;
- what is pseudonymized/substituted;
- what is generalized;
- what is preserved because it is required for the task;
- why each decision occurred.

Human-facing labels are primary; internal action codes remain available in technical details.

This screen makes the trust boundary explicit **before** external disclosure occurs.

### 4. Resultado

The primary output is the **final locally reconstructed answer**.

The result also shows a simple visual path:

```text
Local → Provider externo → Local
```

The reviewer sees a short summary of protections applied and can optionally choose:

- **`Comparar estratégias`** — B0–B4 educational/research comparison;
- **`Ver detalhes técnicos`** — policy/audit/metrics/provenance.

### 5. Comparar estratégias

B0–B4 are a **secondary explanatory surface**, not the landing experience.

Each treatment receives a short human-readable description before codes/metrics are shown. The comparison should make the disclosure/utility trade-off understandable without assuming project vocabulary.

### 6. Detalhes técnicos

Expose safe technical information when requested:

- treatment/version;
- B4 policy version/matrix cell;
- provider/model mode;
- exposure/conformance/utility summaries;
- reconstruction outcome;
- timing/resource/volume fields;
- safe audit/provenance.

## File upload as a primary capability

Upload is central to the advisor demo, not a deferred convenience.

### Supported path

Implemented by T20's demo-integration slice:

```text
browser -> multipart/form-data POST /documents/preview
        -> DisclosureApplicationService.build_document_request
        -> T12 ingestion adapter -> NormalizedContent -> existing core
```

- direct text remains supported through `POST /disclosure/*`;
- `.txt` / `.md` may be normalized without Docling through the same application boundary;
- PDF/DOCX (and XLSX, which rides the same path) go through the normalized ingestion boundary from T12 / Issue #9; image/OCR is deliberately deferred while PDF/DOCX work;
- Next.js must not depend directly on Docling-specific output structures — it never sees one: the API returns the same `PreviewResponse`/`ExecuteResponse` schemas the text routes return.

### Upload contract

`POST /documents/preview` and `POST /documents/execute` take `multipart/form-data`:

| Field | Required | Meaning |
| --- | --- | --- |
| `file` | yes | the document bytes; the filename extension is the authoritative format key |
| `task` | yes | the reviewer's natural-language question |
| `document_type` | yes | `contract` or `hr_record`, from `GET /documents/types` |
| `analysis_mode` | no | one of the document type's allowlisted modes; defaults to the first |
| `strategy` | no | defaults to `recommended` (B4 — Policy-governed) |

`GET /documents/types` returns the vocabulary so the UI hardcodes none of it. It deliberately does **not** return the domain, policy version or requester role each type resolves to: those are the server's decision, and shipping them to the browser would invite a client to send them back as its own.

There is no single route that uploads and answers in one call. Upload + preview is one request, the confirmed execute is another, and the reviewer's confirmation happens between them. The cost is that a confirmed run uploads the file twice; the alternative — retaining the uploaded document server-side between the two calls — is exactly what the no-persistence rule below forbids.

### Contracts governance

An uploaded contract is never analysed under the server's HR defaults. `document_type=contract` resolves server-side to `domain=contracts`, `policy_version=contracts-v1`, `requester_role=contract_analyst` and one of three allowlisted purposes:

| `analysis_mode` | Effect under `contracts-v1` |
| --- | --- |
| `contract_summary` (default) | least disclosing: `contract_value` and `penalty_amount` keep the `(remove, generalize)` action space |
| `financial_audit` | unlocks `preserve` on `contract_value` only |
| `compliance_review` | unlocks `preserve` on `penalty_amount` only |

The frontend cannot invent policy semantics: it sends two opaque tokens, and anything outside the allowlist is refused rather than defaulted.

### Request size

`ADG_MAX_UPLOAD_BYTES` (default 8 MiB) bounds every request body at the HTTP accepting boundary, before any route or body parser runs — on the declared `Content-Length` and on the streamed byte count, so a client omitting the header cannot stream an unbounded body. It sits below the ingestion boundary's own 10 MiB ceiling so an oversized upload is refused before any parsing work begins. The rejection is a fixed 413 that echoes no part of the content.

### Upload UX

Show:

- filename;
- file type;
- size;
- processing status;
- clear parsing/validation errors;
- a concise privacy/trust-boundary explanation.

Processing states should describe the current step, for example:

- `Lendo o arquivo`;
- `Detectando dados sensíveis`;
- `Aplicando política de divulgação`;
- `Consultando o modelo`;
- `Reconstruindo a resposta`.

Advisor-uploaded source documents should **not be persistently stored by default** in the demo.

Uploaded/free-form input remains subject to metadata-only logging, safe error handling and existing no-leak guarantees.

## Provider UX

The primary flow should not require a reviewer to select provider/model.

- use the configured recommended mode by default;
- provider/model selection is an advanced control;
- FakeProvider is clearly identified as deterministic/reproducible demonstration mode;
- T22 real-provider mode is preferred before broadly sharing the demo URL;
- provider credentials never reach the browser.

The deployed service selects its provider from `ADG_PROVIDER` (see [`provider-configuration.md`](provider-configuration.md)). `ADG_PROVIDER=anthropic` yields `provider_class = external_llm` on both the provider and the default `GovernanceContext`, so no custom service has to be injected; `FakeProvider` remains the default and an unrecognized value fails to start rather than falling back.

## Final application direction

The final application retains the same guided test flow as the main entry point.

Primary navigation:

- **Início**;
- **Testar documento**;
- **Histórico**;
- **Experimentos**;
- **Sobre o método**.

Operational/advanced surfaces such as Policies, Providers and infrastructure/debug belong under **Configurações**, not the primary homepage/navigation.

The final application may add:

- run history;
- document/test history where retention is explicitly enabled;
- experiment dashboards;
- richer B0–B4 comparison;
- provider health/configuration;
- policy inspection;
- audit/provenance exploration.

It must not regress into a console that requires internal project knowledge for basic use.

## Demo work sequence

The parallel demo track remains:

1. **T20 / Issue #28 — application boundary + HTTP API**;
2. **T21 / Issue #29 — guided Next.js UI**;
3. **T25 / Issue #42 — containerized demo/deploy infrastructure**;
4. consume **T22 / Issue #30** real-provider mode when available;
5. consume **T12 / Issue #9** structured ingestion for richer file formats.

This sequence remains parallel to M3.

## Container/deployment objective

The goal is a small reproducible research-demo stack shared by URL, not mass distribution.

```text
browser -> web container -> API container -> external provider
                           -> optional OTEL/Jaeger
```

T25 owns:

- Python API image on supported Python 3.13 runtime;
- Next.js image;
- explicit networking;
- health/readiness checks;
- deployment-safe API origin/CORS configuration;
- server-side-only provider secrets;
- one-command local startup;
- documented hosted deployment path;
- application/core version provenance.

## Security stance

- provider credentials never reach the browser;
- vault mappings remain inside the Python trust boundary;
- logs/audit remain metadata-only by default;
- raw/source views are explicit rather than default;
- uploaded/free-form input must not weaken logging/error/no-leak guarantees;
- frontend-visible configuration contains no secrets/private policy state;
- the UI cannot override frozen scientific treatment/policy/scoring semantics.

## Success criterion

A prospective advisor unfamiliar with the project should be able to receive a URL and, without external instructions:

1. understand the concept in roughly two minutes;
2. use a prepared example or upload/provide supported content;
3. ask a task in natural language;
4. understand what remains local and what crosses the external boundary;
5. receive the final answer;
6. optionally discover B0–B4 and deeper research/technical details.

The demo exists to make the research implementation understandable, inspectable and testable. It consumes the scientific project; it must not drive post-hoc tuning of scientific results.