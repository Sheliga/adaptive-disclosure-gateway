/**
 * TypeScript mirror of the Python application-layer wire contract
 * (`src/adaptive_disclosure_gateway/application/wire.py`) and the request
 * body it accepts (`src/adaptive_disclosure_gateway/api/schemas.py`'s
 * `DisclosureRequestBody`).
 *
 * This module declares TYPES ONLY, plus `CONTRACT_VERSION` and the two
 * closed-set constants the runtime guards in `lib/responseGuards.ts` need
 * (`KNOWN_DISCLOSURE_OUTCOMES`, `DISCLOSURE_SUMMARY_STATUSES`) -- no logic,
 * no mapping, no defaults. Field names and shapes mirror the
 * Python side exactly (snake_case, verbatim), so a response decoded as
 * `JSON.parse` matches these types without any renaming step. See
 * `docs/advisor-demo.md` / CLAUDE.md: the UI never reimplements scientific
 * or security semantics -- it renders what the API returns, so its type
 * layer must not silently diverge from what the API actually sends.
 *
 * `CONTRACT_VERSION` must stay byte-identical to the Python constant of the
 * same name in `application/wire.py` -- it is a published contract
 * identifier, not a version to bump opportunistically.
 */

export const CONTRACT_VERSION = "t20-application-api-v1";

// --- GET /health -----------------------------------------------------------

export interface ProviderHealth {
  provider_class: string;
  model_id: string | null;
  model_snapshot: string | null;
  deterministic_demo_mode: boolean;
}

export interface HealthResponse {
  status: string;
  contract_version: string;
  provider: ProviderHealth;
  treatments_available: string[];
}

// --- GET /examples -----------------------------------------------------------

export interface ExampleSummary {
  example_id: string;
  title: string;
  domain: string;
  purpose: string;
  task: string;
  character_count: number;
}

export interface ExamplesResponse {
  contract_version: string;
  examples: ExampleSummary[];
}

// --- GET /documents/types ---------------------------------------------------

export interface DocumentType {
  document_type: string;
  analysis_modes: string[];
  default_analysis_mode: string;
}

export interface DocumentTypesResponse {
  contract_version: string;
  document_types: DocumentType[];
}

// --- shared preview/execute pieces ------------------------------------------

/**
 * The `DisclosureOutcome` StrEnum values as declared today in
 * `application/contracts.py`. Kept as a plain readonly array (not just a
 * union) so `contracts.test.ts` can diff it against the Python source file
 * on disk -- see that test for the enforcement this backs.
 */
export const KNOWN_DISCLOSURE_OUTCOMES = [
  "removed",
  "pseudonymized",
  "generalized",
  "preserved",
  "blocked",
] as const;

export type KnownDisclosureOutcome = (typeof KNOWN_DISCLOSURE_OUTCOMES)[number];

/**
 * `outcome` is modeled as the known union PLUS an escape hatch
 * (`string & {}`) rather than a bare union or a bare `string`.
 *
 * Why not a bare union: the API is a separate, independently-evolving
 * service (T20). A future outcome added on the Python side must still be
 * *representable* by this type -- otherwise decoding a real response would
 * require an unsound cast (`as DisclosureOutcome`) at the JSON boundary,
 * which defeats the point of typing this at all.
 *
 * Why not a bare `string`: that would erase the known members entirely and
 * silence every switch/lookup exhaustiveness signal in `outcomes.ts`.
 *
 * `string & {}` is a widened-string trick: TypeScript keeps the literal
 * members as the *preferred* completions/narrowing target while still
 * accepting any other string, without collapsing the whole type to `string`
 * (which `KnownDisclosureOutcome | string` would do). This is exactly the
 * shape the fail-closed mapping in `outcomes.ts` depends on: it can switch
 * on the known members and must have a real "otherwise" branch for
 * anything else, enforced by `outcomes.test.ts`.
 */
export type DisclosureOutcome = KnownDisclosureOutcome | (string & {});

export interface CategoryDisclosureSummary {
  category: string;
  outcome: DisclosureOutcome;
  action: string;
  crosses_trust_boundary: boolean;
  occurrence_count: number;
  required_for_task: boolean | null;
  technical_reason: string;
  policy_version: string | null;
  policy_restricted: boolean | null;
  impossible_under_policy: boolean | null;
}

/**
 * The `DisclosureSummary.status` values, as `application/contracts.py`
 * declares them today (`Literal["allowed", "blocked"]`).
 *
 * A readonly array rather than a bare union for the same reason
 * `KNOWN_DISCLOSURE_OUTCOMES` is one: `lib/responseGuards.ts` has to check
 * this set at RUNTIME, and `contracts.test.ts` diffs it against the Python
 * source on disk so the two cannot drift.
 *
 * Unlike `outcome`, this set has no escape hatch for an unrecognized value.
 * That is deliberate and is the opposite call from `DisclosureOutcome`
 * above: an unknown outcome degrades safely to "unknown -- verify", but
 * `status` is what decides whether a send is permitted at all, and there is
 * no third rendering between "may send" and "must not send". A status this
 * UI does not know is therefore a rejected response, not a degraded one.
 */
export const DISCLOSURE_SUMMARY_STATUSES = ["allowed", "blocked"] as const;

export type DisclosureSummaryStatus = (typeof DISCLOSURE_SUMMARY_STATUSES)[number];

export interface DisclosureSummary {
  status: DisclosureSummaryStatus;
  categories: CategoryDisclosureSummary[];
  detected_span_count: number;
  detected_categories: string[];
}

export interface SafeGovernanceView {
  domain: string;
  purpose: string;
  policy_version: string;
  provider_class: string;
  requester_role: string | null;
  requested_pseudonym_scope: string;
}

export interface ProviderMode {
  provider_class: string;
}

// --- POST /disclosure/preview -----------------------------------------------

export interface PreviewResponse {
  contract_version: string;
  summary: DisclosureSummary;
  external_payload: string;
  payload_byte_count: number;
  treatment: string;
  strategy: string;
  governance: SafeGovernanceView;
  provider_mode: ProviderMode;
  /**
   * The T27 / issue #69 visual diff/inspector projection. `null` whenever
   * the deployment has `ADG_ENABLE_DEMO_TRANSPARENCY` off (the historical,
   * pre-T27 behavior for every existing caller) -- never absent, always
   * either `null` or a full `DisclosureInspection`.
   */
  inspection: DisclosureInspection | null;
}

/** Structured-upload preview: the normal safe preview plus an opaque proof. */
export interface DocumentPreviewResponse extends PreviewResponse {
  confirmation_token: string;
}

// --- T27 / issue #69: visual diff / transformation inspector ----------------

/**
 * The `DisclosureAction` (`domain.py`) string values that can appear on an
 * `InspectionSegment.action` for a segment that was actually transformed --
 * i.e. the per-span actions a treatment can apply to a detected value.
 * `BLOCK_REQUEST` and `TASK_DEPENDENT` are deliberately excluded: neither is
 * ever the `action` of an individual `Transformation` the inspector
 * projects (`application/inspection.py`) -- `block_request` stops the whole
 * request before any segment exists, and `task_dependent` is resolved to one
 * of the four members below before a `Transformation` is built. Kept as a
 * plain readonly array (not just a union) so `contracts.test.ts` can pin it
 * against `domain.py`'s `DisclosureAction` on disk, and so
 * `lib/inspectionActions.ts` can check membership at runtime.
 */
export const KNOWN_INSPECTION_ACTIONS = ["preserve", "pseudonymize", "generalize", "remove"] as const;

export type KnownInspectionAction = (typeof KNOWN_INSPECTION_ACTIONS)[number];

/**
 * `action` is modeled the same way `DisclosureOutcome` is above: the known
 * union plus an escape hatch, never a bare union or a bare `string` -- see
 * that type's docstring for why. `null` (a separate case, not part of this
 * union) means the segment was untouched, never an unrecognized action.
 */
export type InspectionAction = KnownInspectionAction | (string & {});

/**
 * One segment of the T27 visual diff/inspector projection
 * (`application/contracts.py`'s `DisclosureInspectionSegment` /
 * `application/wire.py`'s `InspectionSegmentModel`). `action`/`category` are
 * both `null` for an untouched segment -- never independently null/non-null,
 * see `lib/responseGuards.ts`'s invariant check. Segments carry no offsets
 * by design: Python code-point offsets are not JS UTF-16 indices, so the UI
 * must never slice `original`/`disclosed` by any index derived from the API
 * -- it only ever renders these strings and concatenates them in order.
 */
export interface InspectionSegment {
  action: InspectionAction | null;
  category: string | null;
  original: string;
  disclosed: string;
}

/**
 * The T27 visual diff/inspector projection itself
 * (`application/contracts.py`'s `DisclosureInspection` /
 * `application/wire.py`'s `DisclosureInspectionModel`). `segments` is always
 * empty when `available` is `false`. `unavailable_reason` is one of
 * `"blocked"` (the disclosure decision itself blocked the request -- nothing
 * to inspect) or `"alignment_failed"` (the pipeline's own alignment check
 * could not verify the projection is faithful, so it fails closed rather
 * than show a partial/best-effort diff) when `available` is `false`, and
 * `null` when `available` is `true`.
 */
export interface DisclosureInspection {
  available: boolean;
  unavailable_reason: string | null;
  segments: InspectionSegment[];
}

// --- POST /disclosure/execute -----------------------------------------------

export interface ProviderStage {
  called: boolean;
  provider_class: string | null;
  model_id: string | null;
  model_snapshot: string | null;
  decoding_config: Record<string, unknown> | null;
  transmitted_bytes: number | null;
  response_hash: string | null;
  failed: boolean;
  failure_kind: string | null;
}

export interface ReconstructionStage {
  attempted: boolean;
  reconstructed_hash: string | null;
  changed_from_provider_response: boolean | null;
}

export interface ExecuteResponse {
  contract_version: string;
  status: string;
  summary: DisclosureSummary;
  final_answer: string | null;
  provider: ProviderStage;
  reconstruction: ReconstructionStage;
  treatment: string;
  strategy: string;
  governance: SafeGovernanceView;
  total_ms: number;
}

// --- POST /disclosure/compare -----------------------------------------------

/**
 * `application/contracts.py`'s `CANONICAL_COMPARISON_ORDER`, mirrored as the
 * frozen `b0`-`b4` codes in the exact order `service.compare_strategies`
 * iterates it -- DIRECT, STATIC_SANITIZATION, REVERSIBLE_PSEUDONYMIZATION,
 * TASK_AWARE, POLICY_GOVERNED. `contracts.test.ts` diffs this against the
 * Python source on disk. This is presentation order only: the UI never
 * re-sorts `CompareResponse.entries` by this array -- the API already
 * returns them in this order, and re-sorting here would be exactly the
 * kind of "UI reimplements semantics" CLAUDE.md forbids. It exists so
 * per-strategy copy (`copy.treatments`) can be looked up/iterated in a
 * fixed, tested order for things like a legend, independent of what any
 * given response happens to contain.
 */
export const CANONICAL_COMPARISON_ORDER = ["b0", "b1", "b2", "b3", "b4"] as const;

export type ComparisonStrategyCode = (typeof CANONICAL_COMPARISON_ORDER)[number];

/**
 * The treatment code the real wire emits for each position in
 * `CANONICAL_COMPARISON_ORDER`. `StrategyComparisonEntryModel.from_domain`
 * (`application/wire.py`) serializes `treatment=entry.treatment.value`,
 * and `application/contracts.py`'s `resolve_treatment` (backed by
 * `_STRATEGY_TO_TREATMENT`) maps every one of the five canonical
 * `DisclosureStrategy` values to the `Treatment` of the IDENTICAL `b0`-`b4`
 * code -- `DisclosureStrategy.DIRECT` ("b0") to `Treatment.DIRECT` ("b0"),
 * and so on through `POLICY_GOVERNED`/"b4". So today this equals
 * `CANONICAL_COMPARISON_ORDER` verbatim.
 *
 * That identity is verified against the Python source, not assumed: kept
 * as its own named constant (rather than reusing
 * `CANONICAL_COMPARISON_ORDER` again at each call site) so the assumption
 * is visible by name, and `contracts.test.ts` derives this same
 * strategy-to-treatment-code mapping independently from
 * `resolve_treatment`/`_STRATEGY_TO_TREATMENT` in `application/contracts.py`
 * and `Treatment` in `domain.py`, diffing it against this constant -- so if
 * a future change ever made a canonical strategy resolve to a
 * differently-coded treatment, that drift test fails instead of the
 * runtime guard in `responseGuards.ts` silently accepting or rejecting the
 * wrong thing.
 */
export const CANONICAL_COMPARISON_TREATMENTS: readonly ComparisonStrategyCode[] = CANONICAL_COMPARISON_ORDER;

/**
 * One strategy's entry in a `/disclosure/compare` response. `strategy` is
 * always an explicit `b0`-`b4` code, never `"recommended"` (see
 * `application/contracts.py`'s `StrategyComparisonEntry` docstring), and
 * `treatment` is always the `b0`-`b4` code of the treatment that strategy
 * resolved to (see `CANONICAL_COMPARISON_TREATMENTS` above) -- so both
 * fields are narrowed to `ComparisonStrategyCode` rather than left as bare
 * `string`, unlike the other identifier fields this module mirrors
 * verbatim. This is what lets `responseGuards.ts` and its fixtures be
 * checked by the type system, not just at runtime: a fixture assigning
 * `treatment: "policy_governed"` (a human-readable name, never a real wire
 * value) fails to compile instead of only failing a runtime guard test.
 *
 * `unsafe_control_baseline` is the ONLY field the UI may use to detect the
 * B0 -- Direct control: never `strategy === "b0"`. It is derived
 * server-side from the treatment's own capability marker
 * (`pipeline.UnsafeControlTreatment`), not from a hardcoded identifier
 * comparison, and the UI must not reintroduce that hardcoding on its own
 * side either -- see `outcomes.test.ts`-style pin in
 * `ComparisonScreen.test.tsx`.
 */
export interface StrategyComparisonEntry {
  strategy: ComparisonStrategyCode;
  treatment: ComparisonStrategyCode;
  recommended: boolean;
  unsafe_control_baseline: boolean;
  summary: DisclosureSummary;
  external_payload: string;
  payload_byte_count: number;
}

export interface CompareResponse {
  contract_version: string;
  entries: StrategyComparisonEntry[];
  governance: SafeGovernanceView;
  provider_mode: ProviderMode;
}

// --- error bodies ------------------------------------------------------------

/** The safe body for every non-validation error response (400/404/500). */
export interface ErrorResponse {
  detail: string;
  kind: string;
}

/** One pydantic validation error, stripped of FastAPI's default `input` echo. */
export interface ValidationErrorItem {
  loc: string[];
  type: string;
  msg: string;
}

/** The 422 body shape returned by FastAPI's `RequestValidationError` handler. */
export interface ValidationErrorResponse {
  detail: ValidationErrorItem[];
}

// --- export / restore (T26 / issue #67; gated behind -----------------------
// ADG_ENABLE_DEMO_TRANSPARENCY for the web UI -- T28 / #70). This module
// never spells out either route handler's own upstream path string in
// prose -- see tests/test_demo_deployment_config.py::TestWebExportRestoreIsGated,
// which pins those two literal strings to the route handlers and lib/api.ts
// only.

/**
 * `application/wire.py`'s `ExportResponse`. Deliberately excludes anything
 * that would let the pseudonym -> original mapping travel wholesale: only
 * `restore_handle` (opaque) and `restorable_count`, never the mapping
 * entries themselves. `expires_at` is an epoch-seconds integer, not an ISO
 * string -- the UI formats it for display, never re-derives a security
 * decision from it.
 */
export interface ExportResponse {
  contract_version: string;
  external_payload: string;
  restore_handle: string;
  expires_at: number;
  restorable_count: number;
  treatment: string;
  strategy: string;
  governance: SafeGovernanceView;
}

/**
 * `application/wire.py`'s `RestoreResponse`. Never carries the mapping
 * either -- only the restored text and two counts.
 */
export interface RestoreResponse {
  contract_version: string;
  restored_text: string;
  restored_count: number;
  unresolved_count: number;
}

// --- GET /api/demo/features (web-only; not part of application/wire.py) -----

/**
 * A web-invented, purely presentational endpoint (T28 / issue #70): whether
 * the export/restore UI should render at all, computed server-side from the
 * SAME `ADG_ENABLE_DEMO_TRANSPARENCY` gate the route handlers themselves
 * enforce (`lib/demoTransparency.ts`). Carries no `contract_version` -- it
 * is not part of the Python application-layer wire contract this module
 * otherwise mirrors, and never will be: it exists only so the client knows
 * whether to bother rendering export/restore controls, never to decide
 * anything security-relevant (the route handlers gate that independently,
 * per request, regardless of what this endpoint last reported).
 */
export interface DemoFeaturesResponse {
  demo_transparency_enabled: boolean;
}

// --- request body ------------------------------------------------------------

/** Mirrors `api/schemas.py`'s `GovernanceOverridesBody` field for field. */
export interface GovernanceOverridesBody {
  purpose?: string | null;
  requester_role?: string | null;
  requester_id?: string | null;
  provider_class?: string | null;
  policy_version?: string | null;
  requested_pseudonym_scope?: string | null;
  session_id?: string | null;
  document_id?: string | null;
  request_id?: string | null;
  domain?: string | null;
}

/**
 * The one shared request body for `POST /disclosure/preview` and
 * `POST /disclosure/execute`. `strategy` mirrors
 * `application.contracts.DisclosureStrategy` ("recommended" | "b0".."b4"),
 * kept as a plain string here since this module is types-only.
 */
export interface DisclosureRequestBody {
  text?: string | null;
  filename?: string | null;
  file_content?: string | null;
  example_id?: string | null;
  task?: string | null;
  strategy?: string | null;
  governance?: GovernanceOverridesBody | null;
}
