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

T30 / Issue #82 reorganized this experience into three progressive-disclosure levels, kept
consistent across every screen:

- **Level 1 (user)**: problem, document, question, review, what will be sent, confirmation,
  answer -- no B0–B4/vault/hash/policy vocabulary required.
- **Level 2 (explanation/research)**: transformations, diff/inspector, detected categories,
  strategy comparison, explanation of decisions, B0–B4 when relevant.
- **Level 3 (technical)**: payloads, IDs, policy versions, hashes, metadata, provider info,
  audit, vault/restore surfaces.

These are hierarchy rules applied across the existing screens below, not a mandate for exactly
three components -- a screen may implement more than one level (e.g. Revisão holds Level-1
content directly and Level-2/3 content behind its own disclosures).

### 1. Boas-vindas / Como funciona

The first screen leads with a **plain-language problem statement**: sending a document directly
to an external LLM can disclose unnecessary information, and the gateway controls what is
disclosed before that external call.

It then shows an accessible **trust-boundary flow diagram** (semantic HTML, not an image):

```text
Documento original → Gateway local → Representação divulgada → LLM externo → Resposta → Reconstrução local
```

The first two and the last step are grouped as the **local (trusted) environment**; the middle
three are grouped as **outside the trust boundary** -- each step carries its own group label as
text, so the boundary is legible without relying on color alone.

A compact **PRESERVE / REMOVE / PSEUDONYMIZE / GENERALIZE** explainer follows, each with a tiny
synthetic before → after example, at the concept level only (no vault/scope vocabulary here).

Primary CTA: **`Testar agora`**.

A closed-by-default **`Como funciona a pesquisa?`** disclosure is the only place on this screen
where B0–B4 appear, introduced by their semantic names (Direct, Static Sanitization, Reversible
Pseudonymization, Task-aware, Policy-governed) in canonical order, with an explicit note that a
normal user does not have to choose among them.

### 2. Novo teste

The reviewer chooses one of three entry modes:

- **Usar um exemplo**;
- **Enviar meu arquivo** (drag-and-drop / file picker);
- **Colar texto**.

Then the reviewer states in natural language what the model should do with the content.

The default experience uses the recommended policy-governed strategy. There is no
treatment/strategy/provider/policy selector on this screen; a new user does not need to know
B0–B4 to execute a test.

### 3. Revisão antes do envio

This is the screen the whole product exists for. Level-1 content reads, in this order:

0. T32.3 / Issue #103 -- when the deployment enables request-scoped inspection
   (`ADG_ENABLE_DEMO_INSPECTION`, see "Demonstration surfaces" below), right after
   `O que você pediu` comes **`O que o gateway fez`**: a before/after visible by default,
   read in the order **Original → Transformação local no gateway → Enviado ao modelo externo**,
   with each transformed passage highlighted and labeled in plain language (category on the
   original side, action on the sent side; a removed passage shows `[trecho removido]`). The
   copy states that the transformed side is the representation the gateway prepared for external
   disclosure in this review -- see the "Preview vs. execute" note below for what that guarantee
   does and does not cover across entry modes. It is built only from `preview.inspection.segments`
   (never a string diff) and shows no B0–B4 code, strategy, policy version, technical reason or
   id. If inspection is unavailable it says so plainly (blocked: nothing was released for
   sending; alignment failure: the view could not be produced safely) and never fabricates a
   before/after;
1. what was detected (`O que foi detectado`);
2. what stays local (`O que permanece local`), each item's outcome label already stating what
   happened to it (removed / pseudonymized / generalized / preserved) and why;
3. what the gateway computed for sending to the external LLM (`O que será enviado ao LLM
   externo`), including the byte-exact payload behind its own explicit disclosure (`Ver o
   payload exato que seria enviado`) -- kept out of the DOM, not just visually hidden, until
   opened.

**Preview vs. execute (fix for #103 review, PR #108).** The before/after and the "what will be
sent" section are both built from the `preview` response, and the join checks in
`lib/responseGuards.ts` only prove that the rendered view matches THAT preview's own
`external_payload` exactly -- they say nothing about a later, separate execute call. Whether the
reviewed representation is what actually crosses the boundary depends on entry mode:

- **Enviar meu arquivo (upload)**: structurally guaranteed. `POST /documents/preview` returns a
  confirmation token; `POST /documents/execute` is bound to it and re-verifies the decision
  matches the approved preview before disclosing anything -- "what was approved is what is sent".
- **Colar texto / Usar um exemplo (paste/example)**: not bound. `POST /disclosure/execute`
  independently re-runs the full decision (detector, task analyzer, decision phase) with no token
  linking it back to this preview. The reviewed representation is an exact view of what THIS
  preview computed, but the representation actually sent can differ if anything about the
  decision's inputs changed between preview and confirm.

The UI copy is written to reflect only the guarantee that holds for all modes: "prepared for
disclosure" / "reviewed", never "exactly what is sent" or "exactly what crosses the boundary".

The confirm action states its consequence explicitly (`Confirmar e enviar ao provedor externo`);
a blocked decision renders no confirm action at all.

Below that, two further, more advanced disclosures sit at Level 2 and Level 3 respectively:

- **Level 2** — `Ver a explicação detalhada das transformações`: the T27 transformation
  inspector (original vs. disclosed, segment by segment, with per-segment action, category,
  treatment, strategy and technical reason) -- the detailed, secondary layer under the
  primary before/after above.
- **Level 3** — `Detalhes técnicos e ferramentas de pesquisa`, collapsed by default: the T28
  export/restore panel and the T29 Vault Explorer, framed as research/technical tooling.

The local-vs-sent split is derived only from `category.crosses_trust_boundary`, never from the
outcome code -- see `lib/outcomes.ts`.

### 4. Resultado

The primary output is the **final locally reconstructed answer** -- the single most visually
prominent element on this screen.

Directly under it (T32.3 / Issue #103, when inspection is enabled), a short recap --
`O que aconteceu antes do envio` -- says which transformation the answer came after: how many
passages the gateway handled (counted from the retained preview's `inspection.segments`, no new
request), with the full before/after one click away. Its wording follows
`ExecuteResponse.provider`: when the provider was not called (e.g. blocked) it says nothing was
sent; when the call failed it says the gateway tried and no answer was produced. The read-only
Approved Review (Result → Back) shows the same before/after under "approved for sending" wording.

Then a short, data-derived protections summary (e.g. "N itens protegidos; M
pseudônimos reconstruídos localmente") is computed only from fields already on `ExecuteResponse`
(`occurrence_count`, `reconstruction.attempted`), never invented.

Below that:

- an `Entender o que aconteceu` disclosure holds the simple visual path
  (`Local → Provedor externo → Local`);
- a research section, headed `Comparar estratégias experimentais (B0–B4)`, frames the strategy
  comparison explicitly as a research surface;
- a technical section, headed with the same "Detalhes técnicos e ferramentas de pesquisa"
  framing as Revisão, holds `Ver detalhes técnicos` and the Vault Explorer.

The provider-mode notice (FakeProvider labelling, required by issue #29) stays visible but is
styled to never outcompete the answer.

### 5. Comparar estratégias

B0–B4 are a **secondary explanatory surface**, not the landing experience, and this screen now
opens with an explicit "Superfície de pesquisa" eyebrow label confirming that framing.

Each treatment receives a short human-readable description before codes/metrics are shown. The
comparison should make the disclosure/utility trade-off understandable without assuming project
vocabulary.

### 6. Detalhes técnicos

Opens with a "Nível técnico / auditoria" eyebrow label. Exposes safe technical information when
requested:

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

## Deployment

Delivered by T25 / Issue #42: `compose.demo.yaml`, `docker/api.Dockerfile` and
`web/Dockerfile`, distinct from the root `compose.yaml` (the dev/test harness that mounts the
repository and runs pytest).

### Local one-command startup

```bash
# 1. Copy the example env and fill in only what you need (placeholders only,
#    never commit a real value):
cp .env.example .env

# 2. Deterministic demo mode (no credential, no cost, no network egress):
ADG_PROVIDER=fake docker compose -f compose.demo.yaml up --build
```

`ADG_PROVIDER` is a required compose variable (`${ADG_PROVIDER:?...}`) -- there is no default in
either direction, so a plain `docker compose -f compose.demo.yaml up` with nothing set refuses
immediately rather than silently picking a provider. Once both containers report healthy, open
`http://localhost:3000` (override the host port with `ADG_DEMO_WEB_PORT`).

The web port is published as `127.0.0.1:${ADG_DEMO_WEB_PORT:-3000}:3000` -- bound to loopback
only, never to every host interface. `http://localhost:3000`/`http://127.0.0.1:3000` keep
working for local development, but the port is not reachable from any other machine, including a
VM's public IP. On a hosted VM, the only ports meant to be reachable publicly are Caddy's 80/443
under the `tls` profile (see "Hosted deployment path" below); open only those two on the host
firewall, never 3000.

To stop: `docker compose -f compose.demo.yaml down`.

### Enabling the real Anthropic provider

```bash
export ADG_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
# Required once a provider outside the trust boundary is selected -- see
# provider-configuration.md's "A real provider also requires
# ADG_PREVIEW_CONFIRMATION_SECRET".
export ADG_PREVIEW_CONFIRMATION_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

docker compose -f compose.demo.yaml up --build
```

Every `ADG_ANTHROPIC_*` variable from [`provider-configuration.md`](provider-configuration.md)
is threaded through to the `api` service unchanged (`ADG_ANTHROPIC_MODEL_ID`,
`ADG_ANTHROPIC_MAX_OUTPUT_TOKENS`, `ADG_ANTHROPIC_EFFORT`, `ADG_ANTHROPIC_THINKING`,
`ADG_ANTHROPIC_TIMEOUT_SECONDS`); none of it, and no credential, is ever forwarded to the `web`
service -- the browser only ever talks to the web origin (see `web/lib/proxy.ts`), never the
Python API, so `web` has no legitimate reason to hold any of it.

### Hosted deployment path

The smallest option compatible with a two-container stack and Docling's memory needs is a
single Docker host VM. Steps a human runs once a VM exists (no infrastructure is provisioned by
an agent session -- no hosting credentials exist in that environment):

1. Provision a VM (>=4 GB RAM -- see "Resource use" below for the measured footprint) with
   Docker and the Compose plugin installed, and a public IP.
2. Point DNS (an A/AAAA record) for the chosen hostname at that IP.
3. Clone the repository on the VM and create a `.env` (git-ignored) with `ADG_PROVIDER`,
   `ANTHROPIC_API_KEY`, `ADG_PREVIEW_CONFIRMATION_SECRET` and `ADG_DEMO_DOMAIN` set as above.
4. Open ports 80/443 on the VM's firewall (the `tls` profile terminates TLS itself; it needs no
   separate load balancer).
5. Start the stack with the optional Caddy TLS reverse-proxy profile, which automatically
   requests and renews a certificate for `ADG_DEMO_DOMAIN`:

   ```bash
   docker compose -f compose.demo.yaml --env-file .env --profile tls up -d --build
   ```

   Caddy's certificate/account state is the *only* volume anywhere in `compose.demo.yaml` --
   `api` and `web` remain volume-free, consistent with "no persistent storage of uploaded
   source documents."
6. Verify: `curl -sf https://<ADG_DEMO_DOMAIN>/api/health` reports `"status": "ok"`, then open
   the URL in a browser and run the guided flow with a synthetic document.
7. Share `https://<ADG_DEMO_DOMAIN>` with prospective advisors.

### Live hosted deployment (srv1994437.hstgr.cloud)

A real deployment of the path above exists, on a Hostinger VPS
(`srv1994437.hstgr.cloud`), reachable at
`https://srv1994437.hstgr.cloud/disclosure-gateway/`. It diverges from the
"Hosted deployment path" recipe above in the specifics that matter for
anyone operating it:

- **`compose.prod.yaml`, not `compose.demo.yaml`.** The host is a
  single-vCPU VPS, too small to build the ~2.64 GB api image itself without
  OOM-ing, so this deployment never builds anything on the host. CI
  (`.github/workflows/publish-images.yml`, triggered on push to `master`)
  builds and pushes both images to GHCR; the host only ever runs
  `docker compose -f compose.prod.yaml --env-file .env pull && ... up -d`
  against an explicit `ADG_IMAGE_TAG`.
- **TLS is nginx's, not Caddy's.** The host already runs nginx 1.28 with a
  Let's Encrypt certificate obtained and renewed by certbot (see
  `deploy/nginx/srv1994437.hstgr.cloud.conf` for the versioned record of
  that configuration) -- `compose.prod.yaml` has no `caddy` service and no
  `tls` profile at all, unlike `compose.demo.yaml`. nginx terminates TLS at
  `/` (a static landing page) and reverse-proxies
  `/disclosure-gateway/` to the `web` container, published loopback-only at
  `127.0.0.1:3000`.
- **Served under a subpath, not the domain root.** `ADG_WEB_BASE_PATH`
  defaults to `/disclosure-gateway` in `compose.prod.yaml`, matching the
  same path baked into the web image at build time (`ADG_WEB_BASE_PATH`
  build ARG, see `web/Dockerfile`/`web/next.config.ts`) and the path nginx
  routes to it -- all three must agree, since Next.js's `basePath` cannot be
  changed without rebuilding the image.
- **Inspection on; export/restore and the Vault Explorer off (T32.3 /
  Issue #103).** This URL is public and unauthenticated, so its posture is
  fixed in `compose.prod.yaml` itself, not left to the host's `.env`:
  `ADG_ENABLE_DEMO_INSPECTION: "1"` on both services (the request-scoped
  before/after), while `ADG_ENABLE_DEMO_TRANSPARENCY`,
  `ADG_ENABLE_DEMO_VAULT_EXPLORER` and the restore-handle secret are not
  declared on either service at all -- compose passes only declared
  variables, so no `.env` can switch them on without editing that reviewed
  file. The web export/restore/vault routes therefore answer a fixed 404
  without calling the api, and the api itself answers 503 on export/restore
  and 404 on the vault explorer. See "Demonstration surfaces" below for why.
  Pinned by `tests/test_prod_deployment_config.py` and
  `tests/test_demo_capability_matrix.py`.

**Continuous deployment.** The rollout from a merged commit to this URL is
fully automatic, with no manual panel step: a push to `master` runs
`test.yml` (already required at the `develop -> master` boundary), then
`.github/workflows/publish-images.yml` builds and pushes both images to
GHCR, then `.github/workflows/deploy.yml` fires on that publish's
`workflow_run` completion and rolls the new SHA out. `deploy.yml` resolves
the target Hostinger VM by hostname, then calls the Hostinger API's
"Create new project" endpoint for the `disclosure-gateway` project with the
repository's own `compose.prod.yaml` (read at the same commit the images
were built from) and an `environment` payload of exactly
`ADG_IMAGE_TAG=<sha>` and `ADG_PROVIDER=fake` -- never the demo
transparency/vault-explorer flags. The Hostinger API rejects a `content`
field over 8192 characters (undocumented in its OpenAPI spec; it surfaced as
a real 422 on the first automated deploy, run 35585709567, against
`compose.prod.yaml`'s full ~9020-byte content). `compose.prod.yaml` stays
versioned with all of its explanatory comments -- `deploy.yml` strips
comment/blank lines (`grep -vE '^[[:space:]]*(#|$)'`) before sending, which
is semantics-preserving (pinned in `tests/test_deploy_workflow.py` against a
`yaml.safe_load` comparison of the real file) and brings the payload to
~2.4 KB, and aborts before calling the API if the filtered content still
exceeds the limit. That endpoint *replaces* the existing
project rather than updating it in place, because `update` only re-pulls
whatever tag the current (SHA-pinned) project already references and would
be a silent no-op here; replacing it is the only way to actually change
which image tag runs. The project keeps belonging to the Docker Manager the
whole time -- it stays visible and editable in the Hostinger panel exactly
as before, this workflow just drives the same API the panel does. The
trade-off is a short availability gap on every deploy (roughly the api
image's 120s healthcheck `start_period` plus the time to pull the ~2.6 GB
api image and tear down the old containers) while the replacement project
comes up; `deploy.yml`'s verify step polls both the Hostinger containers
API and the public `/disclosure-gateway` and `/disclosure-gateway/api/ready`
URLs before declaring success. Requires the `HOSTINGER_API_TOKEN` repository
secret (Hostinger API bearer token; no other secret is introduced). Rollback
is `workflow_dispatch` on `deploy.yml` with `sha` set to any prior published
commit SHA (omit it to redeploy the current `master` commit as-is).

### Health checks

Two distinct endpoints, deliberately not one (T25 review finding 2):

- `GET /health` -- **liveness/introspection**, always 200 once the process is serving requests.
  Reports provider class/model and `deterministic_demo_mode`; never calls the provider and never
  reflects readiness. `GET /api/health` on the web origin is a thin proxy to it.
- `GET /ready` -- **readiness**, purely local: no network call, no provider call, no SDK client
  construction. Returns `{"status": "ready"}` with HTTP 200, or `{"status": "not_ready", "reason":
  "<code>"}` with HTTP 503. `reason` is one fixed, closed-vocabulary code, never free text, a
  credential or a config value:

  | `reason` | Meaning |
  | --- | --- |
  | `provider_credential_missing` | `ADG_PROVIDER=anthropic` and its credential environment variable is unset or blank |
  | `provider_sdk_unavailable` | the `anthropic` package is not importable |
  | `confirmation_secret_not_durable` | an external provider is wired with only an ephemeral, per-process preview-confirmation signer |
  | `provider_unrecognized` | the wired provider is not one this deployment recognizes (fail-closed) |

  `FakeProvider` is always ready. `GET /api/ready` on the web origin proxies the same contract.
- Both containers' Docker `HEALTHCHECK` (and `compose.demo.yaml`'s own `healthcheck:`) target
  `/ready`/`/api/ready`, not `/health`/`/api/health` -- so a container reporting healthy actually
  means ready, not merely alive. `compose.demo.yaml` additionally gates `web`'s startup on `api`
  being `service_healthy` under this same corrected definition.
- A fail-closed startup refusal (invalid `ADG_PROVIDER`, or an external provider with no
  `ADG_PREVIEW_CONFIRMATION_SECRET`) still surfaces as the api process exiting immediately, so it
  never reaches either endpoint -- `restart: unless-stopped` retries the exited container rather
  than masking the failure as healthy. A *running* but not-ready api (e.g. `ADG_PROVIDER=anthropic`
  with no `ANTHROPIC_API_KEY`) instead serves `/health` 200 and `/ready` 503, so `docker compose ps`
  shows it `unhealthy` rather than `Exited`, and `web` never starts (`depends_on: service_healthy`
  is never satisfied).

### Running the smoke test

Two distinct opt-in E2E tests live in `tests/test_demo_smoke_e2e.py` (T25 review finding 3),
gated by different environment variables on purpose -- one must pass against `FakeProvider`, the
other must never pass against it:

**Deployment/structural smoke** -- every class except `TestLiveProviderSmoke`. Drives the **web
origin only** -- `/api/health` -> `/api/ready` -> `/api/documents/types` -> multipart
`/api/documents/preview` -> confirmed `/api/documents/execute` -- with synthetic PDF and DOCX
contracts, and asserts the confirmation flow, the B0 -- Direct external-execute refusal (when the
provider is external), the 413 request-size boundary, and that the deployment reports `/api/ready`
ready. A correctly-recorded provider *call* failure (rate limiting, a transient network error) is
an acceptable outcome here -- the point is that the deployment's own wiring behaves correctly
regardless of whether a live external call happens to succeed on any given run. Skipped unless
`ADG_DEMO_SMOKE_BASE_URL` is set:

```bash
ADG_DEMO_SMOKE_BASE_URL=http://localhost:3000 \
  .venv/Scripts/python.exe -m pytest tests/test_demo_smoke_e2e.py -v
```

**Live-provider smoke** -- `TestLiveProviderSmoke` only. Proves the deployment actually reaches a
*real* external provider and gets a real answer back: it fails (never skips) on anything other
than a genuine successful round trip, including a recorded provider failure -- the opposite
tolerance from the structural smoke above. Requires **both** `ADG_DEMO_SMOKE_BASE_URL` and
`ADG_RUN_DEMO_LIVE_PROVIDER_SMOKE=1`; setting only one of the two skips it. Run it only against a
deployment with `ADG_PROVIDER=anthropic` and a working credential -- it costs real money:

```bash
ADG_DEMO_SMOKE_BASE_URL=https://<ADG_DEMO_DOMAIN> \
ADG_RUN_DEMO_LIVE_PROVIDER_SMOKE=1 \
  .venv/Scripts/python.exe -m pytest tests/test_demo_smoke_e2e.py::TestLiveProviderSmoke -v
```

### What is persisted

Nothing document-related. `api` and `web` mount no volume; an uploaded file is read into memory,
normalized, disclosed and discarded within one request -- never written to disk. The *only*
volume in `compose.demo.yaml` holds Caddy's TLS certificate/account state under the optional
`tls` profile.

### Reproducible dependencies (T25 review finding 4)

The api image's full resolved runtime dependency closure -- every direct and transitive
dependency pip resolves for the base project plus its `api`/`documents`/`anthropic` extras, not
only the ones `pyproject.toml` names directly -- is pinned to exact `name==version` in
[`docker/api-constraints.txt`](../docker/api-constraints.txt). `docker/api.Dockerfile` passes it
to every `pip install` with `-c` (a constraint, never a requirement: it cannot add a package pip
was not already going to install, it only pins the version once pip decides to install it), so
two builds of the same commit resolve the identical dependency set instead of drifting with
whatever the package index happens to serve that day. `torch`/`torchvision` are pinned to their
exact CPU-build version (`+cpu` local version identifier); the Dockerfile also keeps the CPU wheel
index (`https://download.pytorch.org/whl/cpu`) explicit so the *source* of the wheel stays
documented, not only its version.

`tests/test_docker_reproducibility.py` enforces this stays true: every `pyproject.toml` runtime
dependency (base `dependencies` plus the `api`/`documents`/`anthropic` extras) must have a pin in
the constraints file, so adding a dependency without refreshing the lock fails the local test
suite rather than silently shipping unpinned. T26 / issue #67 added `cryptography>=44,<51` as a
base dependency (the sealed restore handle) after this file (T25) merged first; reconciling T26
with `develop` regenerated `docker/api-constraints.txt` accordingly -- only `cryptography` and its
own transitive `cffi`/`pycparser` were added, every pre-existing pin held unchanged.

Regenerate after any dependency change:

```bash
docker build --target builder -f docker/api.Dockerfile -t adg-constraints-builder .
docker run --rm adg-constraints-builder pip freeze --exclude adaptive-disclosure-gateway \
  > docker/api-constraints.txt
# restore docker/api-constraints.txt's header comment (pip freeze emits no comments),
# then rebuild to confirm the constrained install still resolves cleanly:
docker compose -f compose.demo.yaml build --no-cache
```

Base images are pinned by exact tag **and** digest (a tag alone can be republished to point at a
different image later; the digest is the only immutable part of the reference):

| Image | Pinned reference |
| --- | --- |
| api base | `python:3.13.13-slim@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286` |
| web base | `node:24.21.0-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553` |
| caddy (`tls` profile) | `caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648` |

Refresh a digest by pulling the tag and reading it back: `docker pull <image>:<tag>` then
`docker inspect --format='{{index .RepoDigests 0}}' <image>:<tag>`.

This pins dependency *versions* and image *references* only -- no scientific/experimental
semantics changed.

### Resource use (measured, FakeProvider stack, this environment)

| | |
| --- | --- |
| `adg-demo-api` image size | ~2.64 GB (CPU-only torch + Docling + transformers) |
| `adg-demo-web` image size | ~438 MB |
| API container steady-state memory (models resident, idle/light load) | ~330-345 MiB |
| API container cold start to `healthy` (fresh `docker compose up` after the image is built) | ~1s; single preview+execute round trip on the first request after a cold start, ~1.8s |

A 4 GB VM is a comfortable floor; the measured API footprint leaves headroom for the web
container and the OS. Numbers above are from a local Docker Desktop run of the FakeProvider
stack, not a production host -- re-measure before committing to a specific hosted VM size.

### Known limitations

- No authentication: treat a shared demo URL as unlisted-but-not-secret, and set a spend limit
  on the Anthropic account/key used, since anyone with the link can run real-provider requests.
- Two T21 non-blockers carry over unchanged: no document-aware B0-B4 comparison for uploaded
  files yet (comparison stays available for examples/pasted text), and the selected file's type
  label can remain in the previous locale until reselection after a language switch.
- Live Anthropic smoke through a hosted URL is **pending** -- no Anthropic credential exists in
  the environment this deployment work was implemented in. T25/the Demo Track (#41) is not
  complete until a hosted URL is published and a live Anthropic smoke test has run against it
  with a synthetic contract.

## Export and deferred restore (T26 / Issue #67)

The API and CLI offer a way to take a document's disclosed representation
outside the gateway and later restore its pseudonyms locally:
`POST /documents/export` / `POST /documents/restore` and `adg export` /
`adg restore`. Export returns the same disclosed text `preview` already
shows, plus a sealed, stateless restore handle (see
`docs/adr/0002-deferred-restore-handles.md`); restore takes arbitrary text
plus that handle and replaces only the pseudonyms the handle recognizes.
Nothing is retained server-side between the two calls — the handle alone
carries what restore needs, so it works across a restart or a different
worker.

The API/CLI path described above is unconditionally available (subject only
to `ADG_RESTORE_HANDLE_SECRET` being configured, below). A **gated** web
proxy route and UI action for this same mechanism now exist too, behind
`ADG_ENABLE_DEMO_TRANSPARENCY` -- see the "Demonstration surfaces (T27/T28)"
section below for the web-facing walkthrough and why it defaults off.

Configuration: `ADG_RESTORE_HANDLE_SECRET` and `ADG_RESTORE_HANDLE_TTL_SECONDS`
on the `api` service only (never `web`), both optional. Unset
`ADG_RESTORE_HANDLE_SECRET` does not block startup and does not affect any
other route -- `POST /documents/export` and `POST /documents/restore` return
503 until a secret is configured, exactly as described in `.env.example`.
`GET /ready` never consults the restore-handle secret either, so leaving it
unset never makes the deployment report not-ready -- only the export/restore
routes themselves refuse.

## Demonstration surfaces (T27 / Issue #69, T28 / Issue #70, T29 / Issue #72)

Three additive, opt-in demo capabilities, each gated server-side by **its own**
flag and each **off by default** (T32.3 / Issue #103 split the first one out;
until then inspection and export/restore shared `ADG_ENABLE_DEMO_TRANSPARENCY`):

| Capability | Flag | What it is |
| --- | --- | --- |
| Inspection (T27) | `ADG_ENABLE_DEMO_INSPECTION` (api + web) | A request-scoped explanation of content the user submitted themselves: the preview response's `inspection` segments, shown as the Review before/after. |
| Transparency (T28) | `ADG_ENABLE_DEMO_TRANSPARENCY` (web only) | Export/restore -- a separate **re-identification** capability: any text plus a handle is turned back into originals. |
| Vault Explorer (T29) | `ADG_ENABLE_DEMO_VAULT_EXPLORER` (api + web) | A separate **vault inspection** capability: stored originals behind one preview's pseudonyms. |

None implies another, in either direction; all three use the same exact
parsing rule (enabled iff the value, stripped, is exactly `"1"`; `true`,
`yes`, `0`, blank and unset are all disabled). Every server-side gate is
enforced where the capability is served -- hiding a button in the UI never
replaces a route gate. The UI renders each surface only when
`GET /api/demo/features` reports it; a failed or invalid features response
turns every optional surface off.

**Security reason for the separation.** Inspection returns, in the caller's
own preview response, only the original/disclosed segments of the content
that same caller just submitted in that same request -- it discloses nothing
the caller did not already send, so it is safe on the public advisor URL.
Restore and the Vault Explorer reach beyond the request: a reachable restore
endpoint turns a guessed or observed pseudonym back into its original, and
the Vault Explorer reveals stored originals -- both are re-identification
oracles for whoever can reach the web origin. Coupling them to inspection
meant the public demo could not explain a transformation without also
opening re-identification; separate flags let `compose.prod.yaml` enable
the first and keep the other two closed.

They are demonstration/pedagogical features, not part of the core gateway
mechanism, and a final product would remove or significantly restrict them
(see "Demo vs final product" below).

### T27 — Transformation inspector

When `ADG_ENABLE_DEMO_INSPECTION` is enabled, `POST /disclosure/preview`'s and
`POST /documents/preview`'s responses carry a populated `inspection` field
(`null` when the flag is off, on every response, always). The web Review
screen shows it first as the primary before/after (`O que o gateway fez`,
see "3. Revisão antes do envio" above) and, one level deeper, as the
collapsed-by-default detailed inspector showing the original text and the
disclosed `external_payload` side by side, segment by segment, each segment
labeled with its action (`preserve`, `remove`, `generalize`,
`pseudonymize`) and category where available.

This is built from the pipeline's own structured output, never a string
diff: `application/inspection.py::build_inspection` walks
`resolve_overlaps(decision.spans)` zipped 1:1 against
`decision.result.transformations` -- the same per-span records every
transforming treatment (B1 — Static Sanitization through B4 —
Policy-governed) already produces to build `external_payload` itself -- and
verifies that concatenating the segments' `original` values reproduces the
source text exactly and concatenating their `disclosed` values reproduces
`external_payload` exactly. A string diff cannot make either guarantee (it
cannot tell two equal occurrences of the same value apart, and it cannot
attribute a segment to the category/action that produced it).

The projection fails closed rather than guessing: `available: false` with
`unavailable_reason: "blocked"` for a blocked decision (there is no
disclosed representation to show), or `"alignment_failed"` for any other
case where the decision's structured metadata does not line up with the
source text closely enough to project safely. B0 — Direct is a deliberate
special case (its one `Transformation` is a synthetic whole-text audit
entry, not a real span) and falls back to one untouched segment covering
the whole text, which is exactly what B0 discloses.

The inspector opens no OTel span of its own, never imports `vault`, and
never returns offsets on the wire -- only reconstructed text segments.

### T28 — Gated export/restore UI

When enabled (and not blocked), the Review screen also renders an
export/restore panel demonstrating T26's full cycle end to end in the
browser:

1. **Export** -- upload a document (export is upload-only in this panel;
   T26's HTTP export endpoint itself is document-only, there is no
   paste-text export path to proxy); the panel calls the gated
   `POST /api/documents/export` web route, which proxies to the api
   service's `/documents/export` exactly as `/documents/preview` does.
2. The response's restore handle is held **only in React state** (never
   `localStorage`/`sessionStorage`, never a URL parameter, never written to
   any log) and shown masked, with copy/download-to-clipboard actions so an
   advisor can move it out of the browser tab deliberately.
3. **Simulate external use** -- the panel does not call a real external
   service; it lets you copy the disclosed text out, edit it (standing in
   for "this text went through some other tool/process"), and paste the
   result back in.
4. **Restore** -- the panel calls the gated `POST /api/documents/restore`
   web route with the pasted text and the held handle; the response shows
   the restored text plus `restored_count`/`unresolved_count`, never the
   pseudonym → original mapping itself.

Both web routes check the flag **before** doing anything else, including
before inspecting the incoming request -- a disabled flag makes zero
upstream calls to the api service. A third route, `GET /api/demo/features`
(declared `dynamic = "force-dynamic"` so a container's runtime flag value is
never baked in at `next build` time), lets the web UI decide whether to
render the panel at all without exposing any other configuration.

### How to enable it locally

The before/after only (the public advisor posture):

```
ADG_ENABLE_DEMO_INSPECTION=1 \
ADG_PROVIDER=fake docker compose -f compose.demo.yaml up --build
```

Export/restore as well, in a controlled environment only:

```
ADG_ENABLE_DEMO_INSPECTION=1 \
ADG_ENABLE_DEMO_TRANSPARENCY=1 \
ADG_RESTORE_HANDLE_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))") \
ADG_PROVIDER=fake docker compose -f compose.demo.yaml up --build
```

(`ADG_RESTORE_HANDLE_SECRET` is needed only for the T28 export/restore half;
`ADG_ENABLE_DEMO_TRANSPARENCY=1` alone does **not** turn on the before/after.)

To obtain a synthetic document to upload, generate one with the same
fixture builder the test suite uses (values invented at generation time,
never real corpus content):

```
python -c "
import sys; sys.path.insert(0, 'tests')
from document_fixtures import minimal_pdf_bytes
open('demo.pdf', 'wb').write(minimal_pdf_bytes(['Contact John Smith at john.smith@example.com']))
"
```

### Why this defaults off

The hosted demo has no authentication (see "Security stance" below). A
reachable restore endpoint is a re-identification oracle: anyone who can
reach it can submit text containing a guessed or observed pseudonym and get
the original back. Gating export/restore (and, separately, the Vault
Explorer) behind explicit, server-side, non-secret flags means the hosted
URL keeps its default no-authentication posture safely, while a controlled
advisor-evaluation environment can turn the same mechanism on deliberately.
Request-scoped inspection is different in kind -- it only explains the
caller's own just-submitted content back to that caller -- which is why it
has its own flag and is the one capability the public URL enables.

### Demo vs final product

Both surfaces exist to make the gateway's own mechanism visible and
inspectable for pedagogical/scientific evaluation. A final product would
put this behind real authentication/authorization scoped to the document's
own owner, or remove the web-facing inspector/export/restore surfaces
entirely and keep only the API/CLI paths T26 already scopes to a caller who
holds the handle.

### T29 — Vault Explorer

A gated, demo-only local instrument for confirming that reversible
pseudonymization genuinely reverses, entry by entry, for one already-computed
decision. Off by default, gated by its own flag independent of
`ADG_ENABLE_DEMO_TRANSPARENCY`.

**Pedagogical purpose.** T27's inspector shows *what changed* (original →
disclosed segments); T28's export/restore shows *that* T26's mechanism works
end to end via a portable handle. Neither confirms, for one specific
decision, exactly which vault entries a pseudonym in the disclosed payload
maps to, and that local reconstruction genuinely resolves it. The Vault
Explorer closes that gap: for one preview, an operator opens every value
B2 — Reversible Pseudonymization through B4 — Policy-governed pseudonymized,
in place, and sees the original → pseudonym → local scope → reconstruction
chain concretely, without exporting anything or invoking a restore handle.

**How to enable it.** Same non-secret, byte-identical parsing rule as
`ADG_ENABLE_DEMO_INSPECTION` and `ADG_ENABLE_DEMO_TRANSPARENCY` (see `.env.example`): enabled iff the
variable is set and, after stripping whitespace, exactly `"1"`. It is a
fully independent flag -- `ADG_ENABLE_DEMO_VAULT_EXPLORER` does not require
`ADG_ENABLE_DEMO_TRANSPARENCY`, and enabling one never enables or requires
the other. Must be set on **both** `api` and `web`:

```
ADG_ENABLE_DEMO_VAULT_EXPLORER=1 \
ADG_PROVIDER=fake docker compose -f compose.demo.yaml up --build
```

**Advisor walkthrough.**

1. Load a contract or prepared example as usual.
2. Preview under B2 — Reversible Pseudonymization or B4 — Policy-governed;
   the response now also carries an opaque `vault_explorer_token` alongside
   `inspection` (when inspection is also enabled).
3. Open the inspector (T27), if enabled, for the segment-level original vs.
   disclosed view.
4. Open the Vault Explorer panel on Revisão or Resultado. It is collapsed by
   default and fetches nothing until opened.
5. The panel states plainly that the original values stay local: opening it
   makes no upload and calls only `POST /demo/vault-explorer` with the
   token, never a document.
6. Confirm what actually crossed the provider boundary during the real
   preview/execute call was only the pseudonym -- the explorer makes no new
   provider call of any kind.
7. Answer: the panel lists, per pseudonymized value, its category, the
   pseudonym that appeared in the disclosed payload, and -- masked until an
   explicit toggle -- the original the vault resolves it back to locally.
   This is "local reconstruction," made visible.
8. Optionally, use T26/T28's export/restore panel afterward to see the same
   reversibility demonstrated through the durable, sealed-handle mechanism
   instead -- two lenses on one property: live local inspection vs. a
   portable, later-usable handle.

**Scope authorization.** The explorer never accepts a client-chosen scope
id. `POST /documents/preview` seals an opaque, server-generated reference
(`vx1.…`) alongside the decision it just computed; the reference embeds the
resolved scope, that scope's partition key, and this preview's own
PSEUDONYMIZE `(pseudonym, category)` pairs -- each verified against the
vault at issuance time -- and nothing else. A client cannot request a
different scope, another document's entries, or "every entry in scope X":
there is no list-all/enumeration capability, only
`POST /demo/vault-explorer {token}` performing one point lookup
(`vault.reconstruct(scope, key, pseudonym)`) per entry the token itself
names. This is a narrower authorization than the lifecycle identifiers
(e.g. `session_id`) governance overrides elsewhere accept: those select
*which* governed context a request runs under, never *which vault entries*
an already-computed decision may expose. `PseudonymScope.ORGANIZATION` is
excluded outright -- `issue_reference` returns no token at all when the
resolved scope is ORGANIZATION, since an explorer scoped to an entire
organization would defeat the purpose of a per-decision lens.

**Lifecycle.** No persistence anywhere -- not on disk, not in a database,
not in any module-level collection. Each token is sealed with a fresh,
random 32-byte AES-256-GCM key generated once per process, never derived
from `ADG_RESTORE_HANDLE_SECRET`, `ADG_PREVIEW_CONFIRMATION_SECRET`, or any
other configured value. A token expires 900 seconds (15 minutes) after
issuance regardless of activity, and restarting the `api` process
invalidates every outstanding token immediately, since the sealing key dies
with the process. Running multiple `api` workers means a token issued by
one worker fails closed on every other worker -- there is no shared key to
synchronize, by design.

**Difference from T26 restore handles.** A restore handle (T26) is the
authorized, *deferred* re-identification mechanism: meant to outlive the
process that issued it, keyed from a durable configured secret, and
designed to be exported, stored and used later -- possibly on a different
worker or after a restart -- to restore pseudonyms in arbitrary submitted
text. The Vault Explorer is the opposite by design: live, local,
in-process-only instrumentation that makes one already-computed decision's
reversibility visible right now, and dies with the process. The explorer
never decrypts or otherwise touches a restore handle, and neither mechanism
can open the other's envelope -- independent keys, independent formats.

**Difference from T27 inspector.** The inspector shows what changed -- the
original/disclosed text side by side, segment by segment, from the
decision's own structured transformation records; it never touches the
vault and never shows an original value resolved back from a pseudonym. The
Vault Explorer shows which reversible state stayed local -- it is the one
surface that actually calls `Vault.reconstruct`, confirming concretely that
the pseudonym the inspector shows really does resolve back to the original
the inspector shows, via the same local vault the pipeline used. The two
are complementary lenses on one decision: T27 answers "what happened to
this text," T29 answers "prove the reversible part is really reversible,
right here."

**Demo instrument vs. product architecture.** Like T27/T28, this is a
demonstration/pedagogical feature, not a capability the gateway's real API
surface offers by default. It adds no new Vault protocol --
`Vault.reconstruct` is called exactly as `execute`'s own reconstruction path
already calls it, from one new module (`application/vault_explorer.py`)
that is the only application/api-layer code besides the existing execute
path allowed to call it (pinned by
`tests/test_vault_explorer_import_isolation.py`). A final product would
either remove this surface entirely or put it behind real
authentication/authorization scoped to the document's own owner, exactly as
T27/T28's "Demo vs final product" section above already states for those
two surfaces.

**What must never appear in logs/telemetry/audit/browser storage.** Any
original value; any pseudonym beyond what the operator's own current
preview already discloses; the vault-explorer sealing key; a scope's
partition key; the raw token's decoded contents (the opaque `vx1.…` string
itself may appear only in the gated route's own request/response bodies,
never in a log line). The only OTel spans this feature opens
(`vault_explorer.issue`, `vault_explorer.explore`) carry counts only
(`entry_count`, `present_count`) -- never a category, pseudonym, original or
the token. The web panel discards every fetched entry when closed and never
shows an original by default.

### Vault Explorer scope (no global dump/list endpoint)

A gated, demo-only Vault Explorer now exists (T29 / Issue #72, above). What
remains true and unchanged from the T27/T28 design: neither the inspector
nor export/restore lists, browses or dumps the pseudonym → original
mapping, and there is still no endpoint that returns the global mapping or
lets a caller enumerate vault entries outside one decision's own scope.
T29's explorer is deliberately just as narrow -- see "Scope authorization"
above: it performs point lookups against one sealed, per-preview reference,
never a scan of the vault, and every non-demo API continues to return no
mapping at all.

### What must never appear in UI/logs

The full pseudonym → original mapping; the restore-handle secret
(`ADG_RESTORE_HANDLE_SECRET`) or the preview-confirmation secret; the
decoded contents of a restore handle; any original or pseudonym value in a
log line (api access logs, uvicorn logs, Next.js server logs) or an OTel
span attribute; the restore handle itself in a URL or in browser storage
(it lives only in React state for the lifetime of the tab). The same rule
covers T29's Vault Explorer: its opaque `vx1.…` reference, its decoded
entries, and its per-process sealing key must never appear in a log line or
span attribute either -- see the T29 section above for its own scoped list.

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