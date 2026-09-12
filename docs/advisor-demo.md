# Advisor-facing demo application

## Status and purpose

This document defines the **demonstration/application track** for the Adaptive Disclosure Gateway.

The Demo Track is **priority 1**. The sequence is T20 → T21 → T25 → a hosted advisor URL, and
M3 resumes at its next unresolved methodological gate after that URL exists. M3 stands at 5/8
and is **operationally paused**: the pause is scheduling only and changes no frozen scientific
definition, ordering, gate or closure criterion. No post-pilot scorer or date-aware utility
gate is the next active gate.

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
| `confirmation_token` | **execute only, required** | the token the matching preview issued; see *Preview confirmation* below |

`GET /documents/types` returns the vocabulary so the UI hardcodes none of it. It deliberately does **not** return the domain, policy version or requester role each type resolves to: those are the server's decision, and shipping them to the browser would invite a client to send them back as its own.

There is no single route that uploads and answers in one call. Upload + preview is one request, the confirmed execute is another, and the reviewer's confirmation happens between them. The cost is that a confirmed run uploads the file twice; the alternative — retaining the uploaded document server-side between the two calls — is exactly what the no-persistence rule below forbids.

### Preview confirmation

Two separate requests are not, on their own, a review step. Nothing stopped a client previewing
under `recommended`/B4 — Policy-governed with `analysis_mode=contract_summary`, showing the
reviewer that result, and then executing the same upload under `strategy=b0` (B0 — Direct: the
raw document) with `analysis_mode=financial_audit`. **What reached the provider need not have
been what the reviewer approved** — which is the demo's entire guarantee.

`POST /documents/preview` therefore returns a `confirmation_token` alongside the review, and
`POST /documents/execute` requires it. On execute the server re-normalizes the re-uploaded file,
re-resolves the governance and the treatment, computes the disclosure decision for it **once**,
and checks the token against the state that one decision produces. Nothing is read out of the
token and trusted.

That single decision is also the one that is executed: it is handed directly to
`pipeline.execute_disclosure_decision`, the only code that invokes a provider on a disclosure
payload. The payload the token authenticates and the payload the provider receives are one
object, not two objects expected to agree — an assumption that would have rested on the wired
`Detector`/`TaskAnalyzer` happening to be deterministic, and both are replaceable injections.

The token binds, as keyed digests or canonical values and never as raw text: the normalized
document, the task, the document type, the resolved analysis mode, the resolved governance
(domain, policy version, purpose, requester role, pseudonym scope), the strategy and treatment,
the provider class, and the external payload itself. Binding the payload matters — a preview
produced under one detector, treatment implementation, policy resolution or transformation stops
authorising an execute the moment any of those changes, even when every caller-facing parameter
still matches.

| Property | How |
| --- | --- |
| server-authenticated | HMAC-SHA256 over a canonical, key-sorted JSON document, keyed by `ADG_PREVIEW_CONFIRMATION_SECRET`. A client-supplied file hash would prove nothing — a client that changes the strategy can recompute one. |
| stateless | the token carries the proof; the server stores no document, no session and no token. No database, cache or file is introduced. |
| discloses nothing | the token is the semantics version, a `{issued_at, expires_at}` claims object and the MAC. Content is bound as *keyed* digests, never public ones: a public digest of low-entropy content is dictionary-reversible. |
| versioned | every token names `document-preview-confirmation-v1`, so a token issued under one fingerprint rule can never be reinterpreted under a later one. |
| time-boxed | 15 minutes by default. An approval is a review window, not a standing grant. |
| fail-closed | any divergence, tampering, expiry or unknown version is refused with one fixed message, and the provider is never called. |

Known limitation: re-executing the *same* approved state inside the window is accepted.
Preventing that needs a record of spent tokens — storage — which this design deliberately does
not have. The guaranteed property is the one the demo needs: an execute can only ever run a
state a reviewer approved, never a different one.

`ADG_PREVIEW_CONFIRMATION_SECRET` is server-side only and never reaches the browser. A
deployment wired to a provider outside the trust boundary refuses to start without it; with
`FakeProvider`, per-process key material is generated instead, which still enforces confirmation
in full. See [`provider-configuration.md`](provider-configuration.md).

### B0 — Direct on the document surface

B0 — Direct remains fully visible in preview and in the B0–B4 comparison: seeing what an
unprotected disclosure would have looked like is the comparison's whole pedagogical content.

It is **not executable against a provider outside the trust boundary** through
`POST /documents/execute`. That execute fails closed before the provider call, even carrying a
valid B0 confirmation. Against the deterministic `FakeProvider` it still runs, because nothing
leaves the process.

This is a product/demo-surface rule, not an experimental one. B0's experimental semantics are
unchanged, it stays an unsafe control in every comparison, and the T10 experiment runner builds
its own treatments and never passes through this surface. It is the same stance
`compare_strategies` already takes when it refuses to execute any comparison entry, applied to
the one route that can execute an uploaded document.

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

The demo track is priority 1 and runs in this order:

1. **T20 / Issue #28 — application boundary + HTTP API** (demo-integration slice in validation);
2. **T21 / Issue #29 — guided Next.js UI**;
3. **T25 / Issue #42 — containerized demo/deploy infrastructure**;
4. a hosted advisor URL;
5. then M3 resumes at its next unresolved methodological gate.

**T12 / Issue #9** structured ingestion and **T22 / Issue #30** real-provider mode are complete
and are consumed by T20 rather than sequenced after it.

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