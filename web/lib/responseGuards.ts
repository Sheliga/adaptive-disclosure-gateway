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
  CANONICAL_COMPARISON_ORDER,
  CANONICAL_COMPARISON_TREATMENTS,
  CONTRACT_VERSION,
  DISCLOSURE_SUMMARY_STATUSES,
  type CategoryDisclosureSummary,
  type CompareResponse,
  type DemoFeaturesResponse,
  type DisclosureInspection,
  type DocumentPreviewResponse,
  type DocumentType,
  type DocumentTypesResponse,
  type DisclosureSummary,
  type DisclosureSummaryStatus,
  type ExampleSummary,
  type ExamplesResponse,
  type ExecuteResponse,
  type ExportResponse,
  type HealthResponse,
  type InspectionSegment,
  type PreviewResponse,
  type ProviderHealth,
  type ProviderMode,
  type ProviderStage,
  type ReconstructionStage,
  type RestoreResponse,
  type SafeGovernanceView,
  type StrategyComparisonEntry,
  type VaultExplorerEntry,
  type VaultExplorerResponse,
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

function isDocumentType(value: unknown): value is DocumentType {
  return (
    isRecord(value) &&
    isString(value.document_type) &&
    isStringArray(value.analysis_modes) &&
    isString(value.default_analysis_mode) &&
    value.analysis_modes.includes(value.default_analysis_mode)
  );
}

export const isDocumentTypesResponse: ResponseGuard<DocumentTypesResponse> = (
  value: unknown,
): value is DocumentTypesResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  arrayOf(isDocumentType)(value.document_types);

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

// --- T27 / issue #69: DisclosureInspection ----------------------------------

/**
 * `action`/`category` must be null together or non-null together -- an
 * untouched segment carries neither, a transformed one carries both. Never
 * checked against `KNOWN_INSPECTION_ACTIONS`: an action this UI does not
 * recognize is a legitimate response from a newer API, and
 * `lib/inspectionActions.ts` already handles it fail-closed (same posture as
 * `outcome` in `isCategoryDisclosureSummary` above).
 */
function isInspectionSegment(value: unknown): value is InspectionSegment {
  return (
    isRecord(value) &&
    isStringOrNull(value.action) &&
    isStringOrNull(value.category) &&
    isString(value.original) &&
    isString(value.disclosed) &&
    (value.action === null) === (value.category === null)
  );
}

/**
 * Validates the WHOLE `inspection` field of a `PreviewResponse`, including
 * the cross-field invariants a per-interface guard could not express on its
 * own: `segments` is empty whenever `available` is `false`;
 * `unavailable_reason` is a string exactly when `available` is `false` and
 * `null` exactly when it is `true`; and -- the single most important line in
 * this function -- when available, the segments' `disclosed` values
 * concatenate back to EXACTLY `external_payload`. That last check is what
 * makes the inspector trustworthy: without it, a body could claim
 * `available: true` while `segments` describes a different disclosed text
 * than the one the rest of this same response says was actually sent, and
 * every downstream reader (the review screen, this app's own rendering)
 * would have no way to tell. Rejecting the WHOLE response on any of these
 * failing is the same fail-closed posture this module documents at its top:
 * a partially-trustworthy inspection is not rendered as a trustworthy one.
 */
function isDisclosureInspectionField(
  value: unknown,
  externalPayload: string,
): value is DisclosureInspection | null {
  if (value === null) {
    return true;
  }
  if (!isRecord(value) || !isBoolean(value.available)) {
    return false;
  }
  const segments = value.segments;
  if (!arrayOf(isInspectionSegment)(segments)) {
    return false;
  }
  if (!value.available) {
    return segments.length === 0 && isString(value.unavailable_reason);
  }
  if (value.unavailable_reason !== null) {
    return false;
  }
  const reconstructedDisclosed = segments.map((segment) => segment.disclosed).join("");
  return reconstructedDisclosed === externalPayload;
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
  isProviderMode(value.provider_mode) &&
  isDisclosureInspectionField(value.inspection, value.external_payload) &&
  isStringOrNull(value.vault_explorer_token);

export const isDocumentPreviewResponse: ResponseGuard<DocumentPreviewResponse> = (
  value: unknown,
): value is DocumentPreviewResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isPreviewResponse(value) &&
  isString(value.confirmation_token);

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

// --- POST /disclosure/compare ----------------------------------------------------

function isStrategyComparisonEntry(value: unknown): value is StrategyComparisonEntry {
  return (
    isRecord(value) &&
    isString(value.strategy) &&
    isString(value.treatment) &&
    isBoolean(value.recommended) &&
    // The single most important line in this section -- see
    // `contracts.ts`'s `StrategyComparisonEntry` docstring. A truthiness
    // check here (accepting the string "false") would silence the B0
    // warning; a missing field reading as falsy would silence it too.
    isBoolean(value.unsafe_control_baseline) &&
    isDisclosureSummary(value.summary) &&
    isString(value.external_payload) &&
    isNumber(value.payload_byte_count)
  );
}

/**
 * `entries` must be exactly the five canonical strategies, in
 * `CANONICAL_COMPARISON_ORDER`, each one's `treatment` matching the code
 * the real wire emits for that position (`CANONICAL_COMPARISON_TREATMENTS`,
 * pinned against `resolve_treatment` by `contracts.test.ts`). Checking
 * position against the canonical order in a single pass is what handles
 * count, ordering, duplicates and unknown codes together -- any entry
 * whose strategy isn't exactly `CANONICAL_COMPARISON_ORDER[index]` fails
 * this, whether that is because the array is the wrong length, the
 * strategies are reordered, one is repeated, or one is a code this UI does
 * not recognize at all.
 */
function isCanonicalComparisonEntries(value: unknown): value is StrategyComparisonEntry[] {
  return (
    Array.isArray(value) &&
    value.length === CANONICAL_COMPARISON_ORDER.length &&
    value.every(
      (entry, index) =>
        isStrategyComparisonEntry(entry) &&
        entry.strategy === CANONICAL_COMPARISON_ORDER[index] &&
        entry.treatment === CANONICAL_COMPARISON_TREATMENTS[index],
    )
  );
}

export const isCompareResponse: ResponseGuard<CompareResponse> = (
  value: unknown,
): value is CompareResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isCanonicalComparisonEntries(value.entries) &&
  isSafeGovernanceView(value.governance) &&
  isProviderMode(value.provider_mode);

// --- export / restore (T26/#67, gated for the web UI behind ----------------
// ADG_ENABLE_DEMO_TRANSPARENCY -- T28/#70) -----------------------------------

export const isExportResponse: ResponseGuard<ExportResponse> = (
  value: unknown,
): value is ExportResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isString(value.external_payload) &&
  isString(value.restore_handle) &&
  isNumber(value.expires_at) &&
  isNumber(value.restorable_count) &&
  isString(value.treatment) &&
  isString(value.strategy) &&
  isSafeGovernanceView(value.governance);

export const isRestoreResponse: ResponseGuard<RestoreResponse> = (
  value: unknown,
): value is RestoreResponse =>
  isRecord(value) &&
  declaresKnownContractVersion(value) &&
  isString(value.restored_text) &&
  isNumber(value.restored_count) &&
  isNumber(value.unresolved_count);

// --- demo vault explorer (T29 / issue #72) -----------------------------------
//
// `isVaultExplorerResponse` checks TWO cross-field invariants a per-entry
// guard could not express on its own, mirroring `isDisclosureInspectionField`
// above: `entry_count` must equal the actual length of `entries` (never
// trusted as a caller-supplied count that could disagree with the array),
// and `scope === null` must imply `entries` is empty (a null scope means
// "this decision pseudonymized nothing", never "entries exist but their
// scope is unknown"). Each entry's own `present === (original !== null)` is
// checked per-entry: a "present" entry with no original, or an absent one
// that still carries a value, would silently misreport what the local
// vault currently holds.

function isVaultExplorerEntry(value: unknown): value is VaultExplorerEntry {
  return (
    isRecord(value) &&
    isString(value.category) &&
    isString(value.pseudonym) &&
    isStringOrNull(value.original) &&
    isBoolean(value.present) &&
    value.present === (value.original !== null)
  );
}

export const isVaultExplorerResponse: ResponseGuard<VaultExplorerResponse> = (
  value: unknown,
): value is VaultExplorerResponse => {
  if (
    !isRecord(value) ||
    !declaresKnownContractVersion(value) ||
    !isStringOrNull(value.scope) ||
    !isNumber(value.entry_count) ||
    !arrayOf(isVaultExplorerEntry)(value.entries)
  ) {
    return false;
  }
  if (value.entry_count !== value.entries.length) {
    return false;
  }
  if (value.scope === null && value.entries.length !== 0) {
    return false;
  }
  return true;
};

// --- GET /api/demo/features (web-only) ---------------------------------------
//
// No `declaresKnownContractVersion` here -- this response has no
// `contract_version` at all (see `contracts.ts`'s `DemoFeaturesResponse`
// docstring), so it is deliberately absent from `TOP_LEVEL_RESPONSE_GUARDS`
// in `responseGuards.test.ts` too.

export const isDemoFeaturesResponse: ResponseGuard<DemoFeaturesResponse> = (
  value: unknown,
): value is DemoFeaturesResponse =>
  isRecord(value) &&
  isBoolean(value.demo_inspection_enabled) &&
  isBoolean(value.demo_transparency_enabled) &&
  isBoolean(value.demo_vault_explorer_enabled);
