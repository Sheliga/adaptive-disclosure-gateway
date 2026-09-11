# Implementation status

Last updated: 2026-09-11 — T23 post-pilot protocol frozen and corrected per review (`docs/research/post-pilot-protocol-v1.md`); T21 fourth slice (pt-BR / English localization) completed and integrated into `master` via PRs #51/#52 — T21/Issue #29 remains open for the remaining deliberately out-of-scope items.

This file tracks the current engineering/research state and execution order. Architectural decisions belong in ADRs; experimental definitions belong in `docs/experimental-design.md`; factual pilot results belong in `docs/milestone-2-pilot.md`; the frozen confirmatory-analysis protocol belongs in `docs/research/`; the parallel advisor-facing application plan belongs in `docs/advisor-demo.md`; historical PR/Issue descriptions remain in GitHub.

## Current phase

**Milestone 1 and Milestone 2 are complete on `master`.**

The project has moved from building the research treatments to **post-pilot methodological freeze and confirmatory-readiness**.

The canonical sequence is implemented and executable:

**B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed.**

Milestone 2 closed via PR #35 / merge `027a2baead4a3cee35db23cb8d4b79005a3a75d0` after the frozen HR corpus, B3, B4 and the experiment runner were completed.

In parallel, the same Python implementation is now explicitly planned as the **reference application core for an advisor-facing interactive demo**. This application track does not change Milestone 3 gates.

## Milestone 2 — completed

Required scope:

- T09 / Issue #4 — frozen HR minicorpus + oracle ✅
- T07 / Issue #6 — B3 Task-aware ✅
- T08 / Issue #7 — B4 Policy-governed + contextual HR matrix ✅
- T10 / Issue #8 — reproducible runner + first B0–B4 HR pilot ✅

Milestone tracker: Issue #32.

### Frozen implementation / evaluation state

- `corpus/hr/v1/`: 13 controlled HR cases; frozen/versioned.
- B3 frozen implementation commit: `31bce08b7ea6a5c905f7a20bbb4bb99a05682bab`.
- B4 frozen implementation commit: `5abea8514fa10ac64b9bc3714bbfd3f18682f713`.
- B4 retains B3's task-aware baseline and adds contextual policy constraints.
- HR contextual matrix: `hr-v2` / `hr-v3`; original corpus cases remain on frozen `hr-v1`.
- experiment schema: `t10-experiment-runner-v2`.
- artifact bundle schema: `t10-pilot-artifact-bundle-v2`.
- final M2 pilot artifact: `artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/`.

### Runner capabilities delivered

The experiment runner now provides, without sending ground truth into treatments:

- B0–B4 execution over the same case set;
- conformance/policy scoring;
- exposure representation levels;
- binary unnecessary-disclosure scoring;
- detector TP/FP/FN + precision/recall/F1 from the detector spans actually used by execution;
- utility information-sufficiency proxy for FakeProvider runs;
- reconstruction scoring;
- policy-restricted / impossible-under-policy / hard-block outcomes;
- stage-aware latency;
- provider/payload/request byte volume;
- process CPU time and peak Python traced memory;
- B3/B4 implementation provenance;
- B4 policy version/matrix-cell provenance;
- shared `experiment_run_id` plus per-execution ids;
- cross-process deterministic comparison without weakening audit HMAC security;
- safe machine-readable summaries and pairwise comparisons.

The final T10 branch reported 462 passing tests and clean Ruff checks before merge.

## M2 pilot classification

The HR result is **pilot/development evidence**, not held-out confirmatory evidence.

Reasons:

- `corpus/hr/v1` was used during B3/B4 development;
- FakeProvider does not produce real LLM task output, token usage or external API cost;
- the pilot is used to identify methodological decisions that must be frozen before authoritative analysis.

Do not describe M2 as proof that B4 outperforms other treatments.

## Post-pilot findings that now drive planning

Three methodological findings were carried forward without retroactively changing M2, and are
now resolved by the frozen `docs/research/post-pilot-protocol-v1.md`:

1. **Binary unnecessary disclosure penalizes pseudonymization.** The binary rate counts `PSEUDONYMIZE` as transmitted, which can make B2 appear worse than B1 despite a lower representation exposure. **Resolved:** the binary rate is preserved unchanged as a secondary metric; an ordinal/cumulative metric over the existing ordered exposure ladder (per-level proportions and the exceedance distribution `P(exposure >= PSEUDONYMIZE/GENERALIZE/PRESERVE)`, never a mean of ranks) is frozen as primary — the binary rate is recoverable as that family's first threshold (protocol §4).
2. **The main HR B3→B4 pairwise uses `hr-v1`.** Contextual governance effects from `purpose`, `requester_role`, `provider_class` and `policy_version` are identified in targeted `hr-v2/hr-v3` matrix comparisons rather than the main frozen-corpus pairwise run. **Resolved:** the five `hr-v2`/`hr-v3` matrix cells are frozen as the primary B3→B4 comparison; the `hr-v1` pairwise is frozen as secondary/historical (protocol §8).
3. **FakeProvider is not evidence about a real provider.** It remains appropriate for deterministic TDD/pilot reproducibility but cannot support authoritative utility/token/cost or genuine provider-class behavior claims. **Resolved:** valid/invalid uses and the required provenance fields for an authoritative run are frozen, with an explicit no-silent-fallback rule (protocol §9).

The known B3 case `hr_salary_analysis_003/salary` remains intentionally visible: B3 selects `GENERALIZE` while the oracle accepts only `PRESERVE`. It is not tuned away (protocol §12; re-verified at T23 freeze time — 55/56 spans converged).

## Milestone 3 — active

Tracker: Issue #38 — **Post-pilot protocol freeze and confirmatory-readiness**.

### Required research path

Scientific order (frozen by T23, protocol §14 — corrects Issue #36's earlier follow-up comment,
which had placed T24 immediately after T23):

```
T23 → T12 → Contracts domain extensions → T24 → next B0–B4 batch
```

T22 (real provider) proceeds **in parallel** with T12/Contracts/T24: it gates authoritative
utility/token/cost claims (protocol §9), not the Contracts corpus/oracle freeze itself.

#### T23 / Issue #36 — freeze post-pilot methodology

Status: **FROZEN**. `docs/research/post-pilot-protocol-v1.md` (`protocol_id: post-pilot-v1`) is
the authoritative, versioned decision record. It is not rewritten in place; a future
methodological change creates `post-pilot-v2` instead.

Frozen before any confirmatory analysis:

- primary (ordinal/cumulative) and secondary (binary, preserved unchanged) exposure/
  unnecessary-disclosure metrics, both computable from existing runner output; the primary
  metric is exact per-level proportions plus the exceedance distribution
  (`P(exposure >= PSEUDONYMIZE)`, `P(exposure >= GENERALIZE)`, `P(exposure >= PRESERVE)`),
  never a mean of ranks, with the binary secondary metric recoverable as its first threshold —
  a mean of `level_rank` may still be reported, but only as an explicitly-caveated secondary
  descriptive statistic, never as the primary metric;
- interpretation of `PSEUDONYMIZE` relative to representation exposure — the primary metric
  reads the existing ordered ladder (`REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE`,
  `experiments/scoring/exposure.py`) rather than redefining it, and preserves that ladder's
  ordinal (not interval) semantics;
- utility-loss and performance/overhead **interpretation rules** (no numeric threshold could
  be justified from pilot-scale evidence without reverse-engineering it from that evidence, so
  none was invented — see the protocol's §6.4/§7.5);
- primary B3→B4 contextual comparison procedure — the five `hr-v2`/`hr-v3` matrix cells
  (`purpose_salary`, `requester_role_salary`, `requester_role_department`,
  `provider_class_employee_name`, `policy_version_compensation_review`) are frozen as primary;
  the main `hr-v1` pairwise is frozen as secondary/historical (protocol §8);
- provider/model/configuration requirements for an authoritative run, plus the no-silent-
  fallback rule (protocol §9);
- development vs held-out/confirmatory labeling, including the Contracts transition gate
  (protocol §1–§2, with T12 stabilization required before the Contracts *confirmatory* freeze
  and T22 proceeding in parallel to both);
- statistical/descriptive analysis plan — paired, descriptive-only at current sample size, no
  significance ritual the corpus size cannot support, and no specific inferential method
  (bootstrap or otherwise) pre-selected for any future round (protocol §10).

T23 did not tune B3/B4, frozen HR policies, the frozen corpus or M2 artifacts to improve pilot
numbers. Two small enforcement additions back the document: a closed protocol-id registry
(`experiments/post_pilot_protocol.py`) and a regression test pinning that the M2 binary metric
still counts `PSEUDONYMIZE` as transmitted (`tests/test_post_pilot_protocol.py`). The
ordinal/cumulative primary metric's aggregation is specified formally in the protocol but its
implementation in `experiments/aggregation.py` is explicitly deferred to the task that executes
the next confirmatory batch; the runner today reports only the binary rate via
`TreatmentSummary`, plus separate existing rank-based logic
(`aggregation._exposure_rank_sum`) used only for the B3→B4 pairwise's `exposure_direction`,
not for this primary metric.

#### T22 / Issue #30 — real provider

Status: **promoted after M2; may proceed in parallel with T23**.

Implement at least one real provider behind the existing narrow `Provider` protocol. Required before authoritative claims about:

- actual LLM task utility;
- provider tokens;
- external API cost;
- genuine provider/provider-class behavior.

Provider/model/scaffolding/decoding configuration must be frozen under the T23 protocol before confirmatory comparison.

T22 is also consumed by the advisor-facing demo when available. FakeProvider remains sufficient to build/test the demo shell, but a real-provider mode is preferred before sharing the demo broadly with prospective advisors.

#### T12 / Issue #9 — Docling ingestion

Status: **gate released after M2; may proceed in parallel**.

Docling is ingestion infrastructure only. Keep a normalized internal document representation independent from Docling APIs and keep parser behavior constant across B0–B4.

Direct normalized text remains the canonical parser-independent control path.

#### T24 / Issue #37 — Contracts v1 validation corpus

Status: **new second-domain evaluation task; depends methodologically on T23**.

T24 is deliberately separate from T12:

- T12 = document ingestion/normalization infrastructure;
- T24 = frozen Contracts corpus/oracle and evaluation evidence.

If Contracts requires new categories/policies/generalization strategies, those extensions must be frozen before a held-out corpus is inspected at treatment-result level, or the resulting run must remain development evidence.

### Milestone 3 closure criterion

M3 closes when:

1. post-pilot metrics/thresholds/comparison/provider rules are frozen — **done**, `docs/research/post-pilot-protocol-v1.md`;
2. a real provider is available behind the shared boundary;
3. structured Contracts ingestion is available without becoming a treatment variable;
4. Contracts v1 corpus/oracle is frozen with its run classification decided before result inspection;
5. the next B0–B4 batch can start without post-result treatment/policy/metric tuning.

## Parallel academic track

### T01 — PPGCA line/advisor reevaluation

T01 remains independent from engineering gates.

The completed M2 materially changes the academic discussion: the project can now be presented as an executable research prototype with all B0–B4 treatments, a reproducible pilot, machine-readable metrics and explicit methodological limitations—not only as an architecture proposal.

The advisor-facing demo track is intended to make that prototype directly testable by prospective advisors through a hosted URL, but demo completion is not a prerequisite for T01 conversations.

Current provisional candidates remain:

- Daniel Fernando Pigatto;
- Michel Albonico;
- Luiz Celso Gomes Júnior.

T01 blocks only the final academic framing/line/advisor/submission, not M3 engineering.

## Parallel advisor-facing demo/application track

Tracker: **Issue #41 — Advisor-facing interactive research application**.

Purpose: turn the current Python research implementation into the application used to demonstrate the concept to prospective advisors. The demo exposes the actual implemented core rather than recreating anonymization/policy logic in Next.js.

Target path:

```text
browser -> Next.js -> HTTP API -> Python application/core -> B0–B4 -> provider -> local reconstruction
```

### First-demo rules

- no agentic anonymization/orchestration;
- detector/B3 analyzer/B4 policy logic remain the implemented deterministic mechanisms;
- prepared HR examples are synthetic/controlled;
- free-form input, if enabled, must preserve safe logging/error semantics;
- provider credentials remain server-side;
- UI never becomes a source of treatment/policy/scoring semantics.

### T20 / Issue #28 — application boundary + CLI/HTTP/MCP

Status: **first vertical slice in review (PR open) / non-blocking for M3**.

For the advisor demo, HTTP API is the first required adapter. CLI and MCP should share the same application service but do not need to block the first hosted URL.

The HTTP surface should execute controlled text + task + GovernanceContext + treatment/provider through the real Python core and return safe transformation/policy/provider/reconstruction/result metadata.

#### Delivered so far

- `application/` — the shared use-case boundary (`DisclosureApplicationService.preview`/`.execute`), framework-free and reusable by a later CLI/MCP adapter;
- `pipeline.decide_disclosure` — the detect → sanitize → fail-closed-task-check phase extracted from `run_disclosure_case`, so preview and execute share one implementation instead of two;
- `application/ingestion.py` — the normalization seam (direct text, `.txt`, `.md`) that T12 / Issue #9 plugs PDF/DOCX/XLSX/image into behind the same `NormalizedContent` contract;
- `api/` — a thin FastAPI adapter: `GET /health`, `GET /examples`, `GET /strategies`, `POST /disclosure/preview`, `POST /disclosure/execute`, `POST /disclosure/compare`;
- `cli.py` — a thin `argparse` CLI adapter over the same service (`adg health|examples|strategies|preview|execute|compare`), for local development, controlled runs and debugging. No new dependency, and it never imports the HTTP package, so it runs without FastAPI installed;
- `application/wire.py` — the single allowlisted serialization both adapters use, so CLI `--json` and the HTTP API return identical bodies and one field-allowlist governs both surfaces;
- `application/settings.py` — the shared default-service construction both adapters build from.

The default strategy is the policy-governed one, selected as `"recommended"` so the frontend never needs to know B0–B4 to run the primary flow. `GET /strategies` exposes the five treatments for the optional comparison surface.

#### B0–B4 comparison surface

`POST /disclosure/compare` / `adg compare` run the same content through all five treatments in the canonical order and report what each one *would* disclose.

It is **preview-based and never calls a provider**, for any strategy. B0 — Direct discloses the raw document unchanged, so executing a comparison would send the user's unprotected content to the external provider merely to illustrate the teaching point — actively harmful once T22 wires in a real provider, and worthless today since FakeProvider responses carry no task utility. An execute-based/utility-aware comparison is deferred and would require both T22 and a deliberate decision about whether B0 may ever run against a real provider on user content.

This is an **explanatory surface, not an evaluation surface**: it never touches the oracle, never imports `experiments.scoring`, computes no conformance/exposure/unnecessary-disclosure metric, and ranks nothing. Each entry carries `unsafe_control_baseline`, read from the existing `pipeline.UnsafeControlTreatment` capability marker, so B0 can be labeled honestly rather than presented as a peer option.

#### Adapter status

| Adapter | Status |
| --- | --- |
| HTTP API | delivered |
| CLI | delivered |
| MCP | pending |

#### Deliberately still out

MCP adapter, multipart/binary upload, execute-based/utility-aware B0–B4 comparison, real-provider mode (T22 / Issue #30), authentication and rate limiting.

#### Scientific state unchanged

This slice adds no treatment, policy, corpus, oracle or metric semantics. B0–B4, the frozen HR corpus, `hr-v1`/`hr-v2`/`hr-v3`, the M2 artifacts and every experimental metric are untouched; the application layer never reaches the oracle, and the T10 scoring modules are not imported by it.

### T21 / Issue #29 — Next.js advisor-facing UI

Status: **fourth vertical slice completed and integrated into `master`** (PR #51 into `develop`, then PR #52 `develop` → `master`) / non-blocking for M3. T21/Issue #29 is **not** complete and stays open — see "Deliberately not in the fourth slice" below.

The UI lets a reviewer select a prepared HR example or controlled text, see what crosses the trust boundary before anything is sent, receive the locally reconstructed answer, see the same content compared across all five B0–B4 strategies as a preview-only teaching surface, inspect a safe technical/operational view of the SAME execution already shown on Resultado, and — as of the fourth slice — do all of that in either pt-BR or English. It consumes T20's real HTTP API — there is no fixture phase.

#### Delivered in the fourth slice

**pt-BR / English localization**, with the user's choice persisted in the browser. This is a presentation-only change: no Python, contract, B0–B4 treatment, policy, corpus, oracle, endpoint, provider, or execution-behavior code changed.

- **Architecture** — `web/lib/copy.ts` keeps its pre-committed design (module docstring), adjusted for the one thing it hadn't anticipated: `ptBR` ends in `as const`, so `typeof ptBR` alone would produce LITERAL string types and force a second locale to contain the identical Portuguese words. `AppCopy` is instead `Widen<typeof ptBR>` — a recursive mapped type that turns every string literal into `string` and every array into a general `readonly Widen<element>[]`, while leaving object keys untouched. `web/lib/copy.en.ts` defines `export const en: AppCopy = {...}` in its own module; a missing key, an extra key, or a wrong-shaped nested value there is a **compile error**, not a runtime gap (verified by deliberately breaking the file during development: both a missing key and an extra key produced a `tsc` error naming the exact field). `web/lib/copy.ts`'s `resolveCopy(locale)` picks between the two tables.
- **Locale module** (`web/i18n/`) — `locales.ts` (`Locale`, `SUPPORTED_LOCALES`, `DEFAULT_LOCALE`, `isSupportedLocale`, `LOCALE_LABELS`), `localeStorage.ts` (read/write, wrapped in try/catch, mirroring `lib/theme.ts`'s posture toward a throwing `localStorage`), `LocaleContext.tsx` + `LocaleProvider.tsx` (state) + `useLocale.ts` (`useLocale`/`useCopy`, the only way a component reads/changes locale or resolved copy — never `localStorage` directly, never a component-local copy of the state). The context's DEFAULT value (used by any component with no `<LocaleProvider>` ancestor) is a fully working pt-BR value, not `undefined` — every screen unit test written before this slice keeps passing unmodified.
- **Storage key** — `adg-locale`, chosen for consistency with the existing sibling `adg-theme-preference` key (Paulo's suggested example, `adaptive-disclosure-gateway.locale`, was offered as an example rather than a requirement).
- **Hydration mismatch** — handled with `useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)` rather than a mount-effect `setState` (an earlier draft used a `useEffect` that called `setState`, which is correct in outcome but tripped `eslint-plugin-react-hooks`'s `set-state-in-effect` rule; `useSyncExternalStore` is the React-native tool for "an external, client-only data source that can differ between server and client render" and needs no such effect). `getServerSnapshot` (`initialLocale()`) always returns `DEFAULT_LOCALE` and never touches storage — pinned directly in isolation, and further pinned by a real `renderToString` + `hydrateRoot` test that stores `en` beforehand, asserts the server markup is pt-BR, hydrates it, and asserts no `console.error` call matches `/hydrat/i`. `<html lang>` follows the same pattern as `lib/theme.ts`'s `data-theme`: the server always renders `lang="pt-BR"` (`app/layout.tsx`), and `LocaleProvider` updates `document.documentElement.lang` from a `useEffect` once the real locale is known client-side — never read from storage during the first render. Same-tab locale switches are propagated through a small in-module listener set (`storage` events fire only in OTHER tabs).
- **Session locale vs. persistence** — `LocaleProvider.tsx` holds an in-memory `volatileLocale` (module state, `null` until the first `setLocale` call this session) that `getSnapshot` checks BEFORE storage: `volatileLocale ?? readStoredLocale() ?? DEFAULT_LOCALE`. `setLocale` sets it unconditionally and only then attempts `storeLocale` — so a `localStorage.setItem` failure (privacy mode, an embed, a storage policy) can no longer prevent the locale from changing for the rest of the session; it only means the choice does not survive a reload. A `storage` event from another tab still updates `readStoredLocale()`'s return value, but this tab's own explicit choice (if any) keeps winning, since `getSnapshot` checks `volatileLocale` first — a deliberate, simpler-than-cross-tab-sync choice for this slice. `resetVolatileLocaleForTests` (test-only) clears that module state between tests in the same file; `renderWithLocale` and the screens' own `beforeEach`s call it so a switch in one test cannot leak into the next.
- **Locale switcher** (`web/components/LocaleSwitcher/`) — a single real `<button>` next to `ThemeToggle` in `GuidedFlow`'s header, keyboard-operable by construction, text-labeled ("Idioma: Português" / "Language: English" — language names are shown in themselves, never a flag/emoji), toggling between the two supported locales without a reload.
- **Screens covered** — Boas-vindas/Novo teste/Revisão/Resultado/Comparação B0–B4/Detalhes técnicos, plus the shell (theme label, language label) and client-side error messages (`lib/api.ts`'s fallback/validation messages now take an `AppCopy` parameter, defaulting to pt-BR for backward compatibility; `GuidedFlow` passes the live `useCopy()` value at the moment of each user-triggered request).
- **Scientific terminology preserved in English** — B0 stays baseline/reference-control language, never "bad"/"wrong"/"worst"; B4 stays "what it does" language, never "best"/"most secure"/"scientifically superior"; `strategyVsTreatmentExplanation` keeps stating that `recommended` is a request-time option that currently resolves STATICALLY to B4 (never "the policy decides"/"automatically"); `timingExplanation` keeps `total_ms` framed as operational-only, explicitly not the scientific latency metric used in the experiments. `web/lib/copy.test.ts` extends the existing pt-BR regression pins to equivalent English patterns and adds a structural scan (over every string leaf reachable from either locale table) rejecting "best strategy"/"winner"/"most secure"/"scientifically superior" and their pt-BR equivalents, plus a narrower B0-only scan for "bad"/"wrong"/"insecure strategy"/"worst".
- **Technical identifiers unchanged** — `b0`–`b4`, `recommended`, `policy_version`, `provider_class`, contract values, category identifiers, treatment codes, ids, hashes and model ids/snapshots stay byte-identical in both locales; only their human presentation (labels/explanations) changes. Pinned per-screen (e.g. `TechnicalDetailsScreen`'s English test still asserts `"recommended"`/`"b4"` render verbatim).
- **No-leak posture unchanged** — the locale context/provider carries presentation state only (`locale`, `setLocale`, `copy` — no response data); switching locale re-runs the existing adversarial marker tests (an `external_payload` marker planted on Revisão and on Detalhes técnicos) and confirms it still never reaches the DOM; switching locale is pinned to never re-call `/disclosure/preview`, `/disclosure/execute` or `/disclosure/compare`, and to leave the already-held `ExecuteResponse`/`CompareResponse` data unchanged.
- **Key-parity** — enforced primarily by `AppCopy`'s structural type (a compile-time guarantee, verified by intentionally breaking `copy.en.ts` during development); a runtime backstop in `copy.test.ts` additionally walks both locale objects' key paths and asserts they match (with a companion test proving that check can itself fail from a real defect).

#### Delivered in the third slice

**Detalhes técnicos** (`Ver detalhes técnicos`), reached as a secondary action from Resultado, alongside `Comparar estratégias`. Pure client-side navigation over the `ExecuteResponse` Resultado already holds — `lib/flow.ts` gained a `technicalDetails` screen and an `OPEN_TECHNICAL_DETAILS` event; it reuses the existing `RETURN_TO_RESULT` event to go back rather than inventing a second one, and (unlike the comparison screen's return) threads `compareError` through unchanged, since opening/closing this screen never touches comparison state. No new request is made: opening or closing this screen never calls `/disclosure/preview`, `/disclosure/execute` or `/disclosure/compare`.

`components/TechnicalDetailsScreen` takes ONLY `execute: ExecuteResponse` as its data prop (never `preview`) — a structural guard, not just a behavioral one, against `PreviewResponse.external_payload` ever reaching this screen. It renders five sections:

- **Execução** — `strategy` (the requested interface/API choice: `"recommended"` OR an explicit `b0`–`b4` code, both legal on `DisclosureStrategy`) and `treatment` (the `b0`–`b4` code actually executed); `_STRATEGY_TO_TREATMENT` is a static mapping, not a decision procedure — every explicit strategy maps to the treatment it names, and only `recommended` currently resolves (a product/UX default, not a scientific claim that B4 dominates every comparison) to Policy-governed/B4. The screen states this distinction and draws no conclusion from either value;
- **Governança** — only `SafeGovernanceView` fields; a null `requester_role` renders as "Não informado", never as an error;
- **Provedor** — only the safe `ProviderStage` fields. `decoding_config` renders as bounded, non-recursive key/value rows (`formatDecodingValue`, capped at 200 chars), never a dump of the whole response. The not-called state shows only a notice; a failed call shows ONLY `failure_kind` (the safe exception-class-name category — see `audit.py`'s `ProviderStage` docstring) and nothing else provider-related;
- **Reconstrução local** — `attempted`, `changed_from_provider_response`, with a brief explanation of what local reconstruction means; never shows pseudonym mappings or attempts to recover original values;
- **Tempo operacional** — `total_ms`, with explicit pt-BR text stating this is an operational measure of the application run and NOT the scientific latency metric used in the experiments. No T10/`experiments/stage_timing.py` metric, percentile or benchmark is imported, recreated or computed; `total_ms` is never turned into a score.

**Hash tension, flagged for Paulo rather than decided silently:** `response_hash`/`reconstructed_hash` are rendered as technical metadata, but only behind their own nested `<details>` disclosure, kept OUT of the React tree (not merely CSS-hidden) until explicitly opened — the same pattern `ComparisonScreen` uses for `external_payload`. This follows CLAUDE.md's no-leak invariant, which treats a public, reproducible digest of low-entropy content as guessable/dictionary-reversible (one of this project's three historical side-channel defects was exactly an unkeyed public SHA-256 in an audit record). Both hashes are actually HMAC-SHA256 digests keyed by a process-local, non-reproducible secret (`audit.py`'s `_content_hash`/`_DEFAULT_AUDIT_HASH_KEY`), not a plain digest — a materially different risk profile than that historical defect — but the PR leaves the keep/truncate/presence-indicator-only decision to Paulo rather than assuming the keying makes it moot.

`external_payload` does not appear anywhere on this screen; neither do the original document, the task, provider raw response text, pseudonym mappings, or any lifecycle id (`requester_id`/`session_id`/`document_id`/`request_id` — excluded structurally, since `SafeGovernanceView`/`ExecuteResponse` never carry them).

#### Delivered in the second slice

**Comparação B0–B4** (`Comparar estratégias`), reached as a secondary action from Resultado, over `POST /disclosure/compare`:

- teaches before showing codes: each strategy's headline is a plain-language treatment name (`copy.treatments`, derived from `docs/experimental-design.md`'s treatment definitions), with the raw `b0`–`b4` code and `treatment` identifier demoted to an expandable technical-details area;
- states explicitly, in pt-BR, that the comparison is a disclosure simulation and that none of the five strategies sends the document to the provider during this step;
- the B0 — Direct warning is derived from `unsafe_control_baseline` only, never from `strategy === "b0"` — pinned by a test with a non-b0 entry carrying the flag and a b0 entry without it;
- `recommended` renders as "Estratégia recomendada para o fluxo demonstrativo" — product configuration, never a ranking, score or "best" claim; no benchmark table exists;
- reuses `CategoryOutcomeRow`/`describeCategoryOutcome`/`describeCategory` unchanged for the per-strategy local-vs-sent split;
- `external_payload` is kept out of the React tree per strategy until its own disclosure is explicitly opened, same pattern as Revisão's payload toggle; the B0 payload additionally states the unsafe-control context before revealing it;
- entries render in exactly the order `POST /disclosure/compare` returns (`CANONICAL_COMPARISON_ORDER`), pinned against the Python source, never re-sorted client-side;
- `lib/flow.ts` gained `comparing`/`comparison` screens and `REQUEST_COMPARISON`/`COMPARE_SUCCEEDED`/`COMPARE_FAILED`/`RETURN_TO_RESULT` events; returning to Resultado preserves the original `preview`/`execute` state without re-fetching.

Runtime validation added in `lib/responseGuards.ts` (`isCompareResponse`): `contract_version`, the `entries` collection, and per entry `strategy`/`treatment`/`recommended`/`unsafe_control_baseline`/`summary`/`external_payload`/`payload_byte_count`, plus `governance`/`provider_mode`. `unsafe_control_baseline` is checked as a real boolean (`typeof === "boolean"`), matching the existing `crosses_trust_boundary`/`failed` posture — a string `"false"` or an absent field both fail closed.

#### Delivered in the first slice

The guided flow from `docs/advisor-demo.md`, steps 1–4:

1. **Boas-vindas / Como funciona** — the three-step concept explanation;
2. **Novo teste** — prepared example, `.txt`/`.md` upload, or pasted text, plus a natural-language task;
3. **Revisão antes do envio** — what was detected, what stays local vs. what will be sent, per-category plain-language outcome and why;
4. **Resultado** — the reconstructed answer, the `Local → Provedor externo → Local` trust-boundary path, and the protections applied.

Supporting structure under `web/`:

- `lib/contracts.ts` — TypeScript mirror of `application/wire.py`, pinned against the Python enum by a test that reads the Python source;
- `lib/outcomes.ts` — the only place a category summary becomes user-facing text. **Fail-closed**: an outcome the UI does not recognize renders as "unknown — verify", never as protected/local. The local-vs-sent split is read from `crosses_trust_boundary`, never re-derived;
- `lib/copy.ts` — all pt-BR copy in one module, structured so a second locale is an addition rather than a refactor;
- `app/api/**` — thin Next.js proxy routes (`browser → web → API`), forwarding body and status unchanged and never logging either;
- `app/globals.css` — semantic tokens with complete light and dark palettes.

The primary path never requires knowing B0–B4: the UI simply omits `strategy`, so the API's `"recommended"` (policy-governed) default applies. A test pins that the compose screen renders no B0–B4 vocabulary and no treatment selector.

#### Deliberately not in the first slice

`Comparar estratégias` (the B0–B4 screen over `POST /disclosure/compare`), `Ver detalhes técnicos`, the English locale, `Histórico`, `Experimentos` and the `Configurações` area.

#### Deliberately not in the second slice

`Ver detalhes técnicos` (the full technical-details screen — the comparison screen's own per-entry technical disclosure is a small expandable, not that screen), the English locale, `Histórico`, `Experimentos`, `Configurações`, a real provider, auth, rate limiting, and structured PDF/DOCX/XLSX upload.

#### Deliberately not in the third slice

The English locale, `Histórico`, `Experimentos`, `Configurações`, remaining navigation polish, T12 structured-document ingestion (PDF/DOCX/XLSX), T22 real provider, and T25 deploy.

#### Deliberately not in the fourth slice

`Histórico`, `Experimentos`, the full `Configurações` area, remaining navigation polish, locale-aware number/date/byte formatting (kept deliberately simple/out of scope for this slice), T12 structured-document ingestion (PDF/DOCX/XLSX), T22 real provider, and T25 deploy. **T21/Issue #29 stays open** pending these.

#### Scientific state unchanged

The UI adds no treatment, policy, corpus, oracle or metric semantics. It renders what the API returns and never decides what is safe. The comparison screen imports no scoring/oracle/metric module and computes no aggregate across strategies beyond what each strategy's own preview already reports. The technical-details screen computes no scientific metric either: `total_ms` is operational-only, never a substitute for T10's stage-aware latency metric. The fourth slice (localization) is presentation-only: no treatment, policy, corpus, oracle, endpoint, provider or execution-behavior code changed, and the frozen `b0`–`b4` codes/technical identifiers are never translated in either locale.

### T25 / Issue #42 — containerized demo/deploy infrastructure

Status: **backlog / follows functional API+UI integration / non-blocking for M3**.

The current root `compose.yaml` is a development/test harness rather than deploy infrastructure: it mounts the repository and runs tests. T25 owns a distinct deployment-oriented topology.

Required demo infrastructure includes:

- Python API image on the supported Python 3.13 runtime;
- Next.js image;
- demo/deploy compose/profile distinct from test compose;
- service networking;
- health/readiness checks;
- explicit CORS/API-origin handling;
- server-side-only provider secrets;
- one-command local startup;
- documented simple hosted container deployment suitable for sharing a URL;
- core/application version provenance.

The target is a small research-demo deployment, not desktop distribution, installers, multi-tenant SaaS or production-scale orchestration.

### Demo completion criterion

The first demo track is complete when a prospective advisor can receive a URL and execute at least the controlled HR B0–B4 concept through the actual Python core without local setup.

T22/real provider improves this substantially and should be enabled when available, but FakeProvider remains valid for deterministic demonstration of the gateway mechanics.

## Deferred unless evidence creates a need

- persistent/shared `SQLiteVault` or equivalent;
- second real provider for robustness;
- Accounting/Finance third domain;
- multi-turn disclosure-history study;
- additional detector categories not required by the next frozen domain;
- full product-grade visual audit platform;
- agentic anonymization as an unversioned replacement for the deterministic B0–B4 path.

## Execution order

### Critical research path

1. M2 / HR pilot ✅
2. **T23 / Issue #36 — freeze post-pilot protocol**
3. In parallel: **T22 real provider** + **T12 Docling/normalization**
4. **T24 / Issue #37 — Contracts v1 corpus/oracle**
5. Verify M3 closure / confirmatory-readiness
6. Launch next frozen B0–B4 validation batch
7. Only then analyze authoritative comparative results under the pre-frozen protocol

### Parallel academic path

- T01 advisor/line framing.

### Parallel demo/application path

1. **T20 HTTP/application boundary**;
2. **T21 Next.js interactive demo**;
3. **T25 containerized deploy**;
4. consume **T22 real provider** when available.

This ordering is internal to the demo track and does not reorder the scientific critical path.

## References

- Experimental design: `docs/experimental-design.md`
- M2 pilot record: `docs/milestone-2-pilot.md`
- Advisor demo plan: `docs/advisor-demo.md`
- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- M2 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/32
- T23 methodology freeze: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/36
- T22 real provider: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/30
- T12 Docling: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/9
- T24 Contracts corpus: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/37
- M3 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/38
- Demo tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/41
- T20 CLI/API/MCP: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/28
- T21 Next.js UI: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/29
- T25 demo containers/deploy: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/42