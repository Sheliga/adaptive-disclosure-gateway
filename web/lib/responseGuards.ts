/**
 * Runtime validation for every 200 response body this app consumes.
 *
 * --- Why this module exists ---
 *
 * `lib/contracts.ts` describes the wire shapes, but a TypeScript interface
 * is erased at runtime: `(await response.json()) as PreviewResponse` is an
 * assertion, not a check. It tells the compiler what to believe and asks
 * the network nothing. So a 200 whose body does not actually satisfy the
 * contract used to reach the React tree wearing the contract's type, and
 * every downstream read of it was silently unsound.
 *
 * That is not a cosmetic typing concern here, because of WHICH fields the
 * review flow reads and in which direction they fail:
 *
 *  - `crosses_trust_boundary` is the authoritative local-vs-sent split
 *    (`lib/outcomes.ts`). Absent, it decodes as `undefined`, and `undefined`
 *    is falsy -- so a category that DID cross the trust boundary would be
 *    filed under "o que permanece local". The reviewer would be told the
 *    opposite of the truth about their own data.
 *  - `summary.status` gates the confirm-and-send button
 *    (`ReviewScreen`/`ResultScreen` both branch on `=== "blocked"`). An
 *    unknown or missing status is not equal to `"blocked"`, so it would
 *    render as permission to send.
 *  - `provider.failed` gates whether `final_answer` is presented as a real
 *    completion. Absent -> falsy -> "the provider call succeeded".
 *
 * In all three cases the *unchecked* failure mode is the unsafe one. So
 * this module is fail-closed by construction: a body is accepted only when
 * every field the contract declares is present with the declared type.
 * Anything else is rejected wholesale, and `lib/api.ts` maps it to the same
 * generic `ApiFailure` it uses for an unrecognized error shape -- carrying
 * nothing from the rejected body, which may still hold the user's document
 * text (CLAUDE.md's no-leak invariant applied to this boundary).
 *
 * --- Why hand-written guards rather than a schema library ---
 *
 * These guards are the mirror image of `application/wire.py`, which is
 * itself explicitly field-by-field ("explicit response schemas -- never
 * blanket serialization"). Writing them the same way keeps the two sides
 * readable against each other, and adds no runtime dependency to a UI whose
 * whole job is to be a thin, auditable window onto the API. The cost of the
 * hand-written form -- that a field added to `contracts.ts` could be
 * forgotten here -- is removed by `responseGuards.test.ts`, which reads
 * `contracts.ts` off disk and fails if any declared field of a validated
 * response is not named in this file.
 *
 * --- What is deliberately NOT validated ---
 *
 * `outcome` is checked as a string only, never against
 * `KNOWN_DISCLOSURE_OUTCOMES`. An outcome the UI does not recognize is a
 * legitimate response from a newer API, and `lib/outcomes.ts` already
 * handles it correctly and visibly (fail-closed to "unknown -- verify").
 * Rejecting the whole response instead would turn a safely-degradable
 * situation into a hard failure. `summary.status` is the opposite case and
 * IS checked against its closed set, because there is no safe way to render
 * an unknown status: the UI has only "may send" and "must not send".
 *
 * Extra fields are tolerated rather than rejected. The Python models use
 * `extra="forbid"` so extras cannot legitimately appear under the current
 * `contract_version`; and an extra field is by definition one nothing here
 * reads, so refusing it would buy no safety while making an additive
 * contract change break the UI.
 *
 * `contract_version` IS checked for equality with `CONTRACT_VERSION`. That
 * constant exists precisely so "a client can assert compatibility"
 * (`application/wire.py`'s docstring) -- and a body announcing a contract
 * this UI was not written against is exactly the case where guessing at the
 * meaning of its fields is unsafe.
 */

import {
  CONTRACT_VERSION,
  DISCLOSURE_SUMMARY_STATUSES,
  type CategoryDisclosureSummary,
  type DisclosureSummary,
  type DisclosureSummaryStatus,
  type ExampleSummary,
  type ExamplesResponse,
  type ExecuteResponse,
  type HealthResponse,
  type PreviewResponse,
  type ProviderHealth,
  type ProviderMode,
  type ProviderStage,
  type ReconstructionStage,
  type SafeGovernanceView,
} from "./contracts";

/** A runtime check that also narrows -- the shape `lib/api.ts` consumes. */
export type ResponseGuard<T> = (value: unknown) => value is T;

// --- primitives --------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  // `typeof null === "object"`, and an array is an object too. Neither is a
  // JSON object, and both would otherwise pass every `in`-style check below
  // vacuously.
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isBoolean(value: unknown): value is boolean {
  // Strict on purpose: `"false"`, `0` and `1` are NOT booleans here. A
  // truthiness test is what makes the string "false" read as true.
  return typeof value === "boolean";
}

function isNumber(value: unknown): value is number {
  // `NaN`/`Infinity` cannot come out of `JSON.parse`, but they can come out
  // of a hand-built object, and neither is renderable as a byte count.
  return typeof value === "number" && Number.isFinite(value);
}

function nullable<T>(check: (value: unknown) => value is T) {
  return (value: unknown): value is T | null => value === null || check(value);
}

function arrayOf<T>(check: (value: unknown) => value is T) {
  return (value: unknown): value is T[] => Array.isArray(value) && value.every(check);
}

const isStringOrNull = nullable(isString);
const isBooleanOrNull = nullable(isBoolean);
const isRecordOrNull = nullable(isRecord);
const isNumberOrNull = nullable(isNumber);
const isStringArray = arrayOf(isString);

function isKnownSummaryStatus(value: unknown): value is DisclosureSummaryStatus {
  return isString(value) && (DISCLOSURE_SUMMARY_STATUSES as readonly string[]).includes(value);
}

/**
 * Every response model in `application/wire.py` carries `contract_version`.
 * Checking it once, here, is what makes the per-field guards below a
 * statement about a KNOWN contract rather than a guess at an unknown one.
 */
function declaresKnownContractVersion(value: Record<string, unknown>): boolean {
  return value.contract_version === CONTRACT_VERSION;
}

// --- GET /health --------------------------------------------------------------

function isProviderHealth(value: unknown): value is ProviderHealth {
  return (
    isRecord(value) &&
    isString(value.provider_class) &&
    isStringOrNull(value.model_id) &&
    isStringOrNull(value.model_snapshot) &&
    isBoolean(value.deterministic_demo_mode)
  );
}

export const isHealthResponse: ResponseGuard<HealthResponse> = (
  value: unknown,
): value is HealthResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isString(value.status) &&
  isProviderHealth(value.provider) &&
  isStringArray(value.treatments_available);

// --- GET /examples --------------------------------------------------------------

function isExampleSummary(value: unknown): value is ExampleSummary {
  return (
    isRecord(value) &&
    isString(value.example_id) &&
    isString(value.title) &&
    isString(value.domain) &&
    isString(value.purpose) &&
    isString(value.task) &&
    isNumber(value.character_count)
  );
}

export const isExamplesResponse: ResponseGuard<ExamplesResponse> = (
  value: unknown,
): value is ExamplesResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  arrayOf(isExampleSummary)(value.examples);

// --- shared preview/execute pieces ----------------------------------------------

function isCategoryDisclosureSummary(value: unknown): value is CategoryDisclosureSummary {
  return (
    isRecord(value) &&
    isString(value.category) &&
    // Not narrowed to the known outcomes -- see the module docstring.
    isString(value.outcome) &&
    isString(value.action) &&
    // The single most important line in this module.
    isBoolean(value.crosses_trust_boundary) &&
    isNumber(value.occurrence_count) &&
    isBooleanOrNull(value.required_for_task) &&
    isString(value.technical_reason) &&
    isStringOrNull(value.policy_version) &&
    isBooleanOrNull(value.policy_restricted) &&
    isBooleanOrNull(value.impossible_under_policy)
  );
}

function isDisclosureSummary(value: unknown): value is DisclosureSummary {
  return (
    isRecord(value) &&
    isKnownSummaryStatus(value.status) &&
    arrayOf(isCategoryDisclosureSummary)(value.categories) &&
    isNumber(value.detected_span_count) &&
    isStringArray(value.detected_categories)
  );
}

function isSafeGovernanceView(value: unknown): value is SafeGovernanceView {
  return (
    isRecord(value) &&
    isString(value.domain) &&
    isString(value.purpose) &&
    isString(value.policy_version) &&
    isString(value.provider_class) &&
    isStringOrNull(value.requester_role) &&
    isString(value.requested_pseudonym_scope)
  );
}

function isProviderMode(value: unknown): value is ProviderMode {
  return isRecord(value) && isString(value.provider_class);
}

// --- POST /disclosure/preview ----------------------------------------------------

export const isPreviewResponse: ResponseGuard<PreviewResponse> = (
  value: unknown,
): value is PreviewResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isDisclosureSummary(value.summary) &&
  isString(value.external_payload) &&
  isNumber(value.payload_byte_count) &&
  isString(value.treatment) &&
  isString(value.strategy) &&
  isSafeGovernanceView(value.governance) &&
  isProviderMode(value.provider_mode);

// --- POST /disclosure/execute ----------------------------------------------------

function isProviderStage(value: unknown): value is ProviderStage {
  return (
    isRecord(value) &&
    isBoolean(value.called) &&
    isStringOrNull(value.provider_class) &&
    isStringOrNull(value.model_id) &&
    isStringOrNull(value.model_snapshot) &&
    isRecordOrNull(value.decoding_config) &&
    isNumberOrNull(value.transmitted_bytes) &&
    isStringOrNull(value.response_hash) &&
    // Gates whether `final_answer` is shown as a real completion.
    isBoolean(value.failed) &&
    isStringOrNull(value.failure_kind)
  );
}

function isReconstructionStage(value: unknown): value is ReconstructionStage {
  return (
    isRecord(value) &&
    isBoolean(value.attempted) &&
    isStringOrNull(value.reconstructed_hash) &&
    isBooleanOrNull(value.changed_from_provider_response)
  );
}

export const isExecuteResponse: ResponseGuard<ExecuteResponse> = (
  value: unknown,
): value is ExecuteResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isString(value.status) &&
  isDisclosureSummary(value.summary) &&
  isStringOrNull(value.final_answer) &&
  isProviderStage(value.provider) &&
  isReconstructionStage(value.reconstruction) &&
  isString(value.treatment) &&
  isString(value.strategy) &&
  isSafeGovernanceView(value.governance) &&
  isNumber(value.total_ms);
