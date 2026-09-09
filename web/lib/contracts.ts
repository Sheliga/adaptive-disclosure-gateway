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
