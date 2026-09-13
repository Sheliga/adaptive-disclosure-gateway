/**
 * Typed client over this app's own `/api/**` proxy routes (never the Python
 * API directly -- see `lib/proxy.ts`'s module docstring for the topology).
 * Thin wrappers only: no business logic, no retries. Every call returns a
 * discriminated `ApiResult<T>` so screens branch on `.ok` instead of
 * handling a raw `Response`/thrown error.
 *
 * Both directions of the boundary are gated, and gated the same way.
 *
 * A SUCCESS body is not trusted for having arrived with a 200: it must
 * satisfy the matching guard in `lib/responseGuards.ts` before it becomes
 * `ApiSuccess.data`. `(await response.json()) as T` would be a compile-time
 * assertion only, and the fields this app reads fail unsafely when absent
 * -- a missing `crosses_trust_boundary` reads as falsy, i.e. "stayed
 * local"; a missing `summary.status` is not `"blocked"`, i.e. "may send".
 * See that module's docstring for the full argument. A 200 that fails its
 * guard collapses to the same generic `ApiFailure` as any other
 * unrecognized body -- it never reaches a caller as data.
 *
 * Error mapping is the one piece of judgment this module makes, and it is
 * deliberately conservative: `application/wire.py`'s `ErrorResponse`
 * (`{detail, kind}`) and the 422 `ValidationErrorResponse` (`{detail: [...]}
 * `) are the only two shapes the Python API's own no-leak boundary
 * guarantees are safe to display verbatim (see `api/app.py`'s module
 * docstring). Anything that does not parse as JSON, or parses but matches
 * neither known shape, is NOT trusted and NOT surfaced -- it collapses to
 * `copy.errors.generic` instead. This is the same fail-closed posture as
 * `outcomes.ts`: an unrecognized shape must never be assumed safe to show
 * just because it happened to arrive as this response's body.
 *
 * One rule covers both directions: a body this module could not fully
 * understand contributes NOTHING to what the user sees. Not a fragment of
 * it, not a field name from it, not a hint about which check failed --
 * a rejected body can still hold the user's document text (CLAUDE.md's
 * no-leak invariant), so the failure it maps to is a fixed, content-free
 * value.
 */

import type {
  CompareResponse,
  DemoFeaturesResponse,
  DisclosureRequestBody,
  DocumentPreviewResponse,
  DocumentTypesResponse,
  ExamplesResponse,
  ExecuteResponse,
  ExportResponse,
  HealthResponse,
  PreviewResponse,
  RestoreResponse,
} from "./contracts";
import type { AppCopy } from "./copy";
import { copy as defaultCopy } from "./copy";
import {
  isCompareResponse,
  isDemoFeaturesResponse,
  isDocumentPreviewResponse,
  isDocumentTypesResponse,
  isExamplesResponse,
  isExecuteResponse,
  isExportResponse,
  isHealthResponse,
  isPreviewResponse,
  isRestoreResponse,
  type ResponseGuard,
} from "./responseGuards";

export interface DisplayError {
  /** Safe, display-ready message -- never raw upstream prose. */
  message: string;
  /** The upstream exception class name, when known (e.g. "IngestionError"). */
  kind: string | null;
  /** Per-field validation issues, only present for a 422 response. */
  fields: { loc: string[]; type: string }[] | null;
}

export interface ApiSuccess<T> {
  ok: true;
  data: T;
}

export interface ApiFailure {
  ok: false;
  status: number;
  error: DisplayError;
}

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

function isErrorResponseShape(value: unknown): value is { detail: string; kind: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).detail === "string" &&
    typeof (value as Record<string, unknown>).kind === "string"
  );
}

function isValidationErrorResponseShape(
  value: unknown,
): value is { detail: { loc: string[]; type: string; msg: string }[] } {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const detail = (value as Record<string, unknown>).detail;
  if (!Array.isArray(detail)) {
    return false;
  }
  return detail.every(
    (item) =>
      typeof item === "object" &&
      item !== null &&
      Array.isArray((item as Record<string, unknown>).loc) &&
      typeof (item as Record<string, unknown>).type === "string",
  );
}

function genericError(appCopy: AppCopy): DisplayError {
  return { message: appCopy.errors.generic, kind: null, fields: null };
}

async function toDisplayError(response: Response, appCopy: AppCopy): Promise<DisplayError> {
  if (response.status === 413) {
    return { message: appCopy.errors.fileTooLarge, kind: "RequestTooLarge", fields: null };
  }
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    return genericError(appCopy);
  }

  if (response.status === 422 && isValidationErrorResponseShape(parsed)) {
    return {
      message: appCopy.errors.validationFailed,
      kind: null,
      fields: parsed.detail.map((item) => ({ loc: item.loc, type: item.type })),
    };
  }

  if (isErrorResponseShape(parsed)) {
    const known: Record<string, string> = {
      IngestionError: appCopy.errors.documentParsing,
      DocumentAnalysisPresetError: appCopy.errors.invalidAnalysisMode,
      PreviewConfirmationError: appCopy.errors.previewExpired,
      UpstreamUnreachable: appCopy.errors.upstreamUnreachable,
      // T27/T28 (issues #69-#70): the demo transparency gate and T26's
      // export/restore refusal kinds. Every one of these carries a fixed,
      // safe `detail` from the Python side already (CLAUDE.md's no-leak
      // invariant), but this app still prefers its own copy over the raw
      // upstream string for the same reason every other kind above does --
      // consistent phrasing/locale, and one fewer place a future upstream
      // wording change could surface unreviewed prose to the user.
      DemoTransparencyDisabled: appCopy.errors.demoTransparencyDisabled,
      ExportRefusedError: appCopy.errors.exportRefused,
      RestoreUnavailableError: appCopy.errors.restoreUnavailable,
      RestoreHandleInvalidError: appCopy.errors.restoreHandleInvalid,
      RestoreHandleExpiredError: appCopy.errors.restoreHandleExpired,
    };
    return { message: known[parsed.kind] ?? parsed.detail, kind: parsed.kind, fields: null };
  }

  // Parsed fine but matches neither contract this app trusts -- fail
  // closed rather than displaying an unrecognized shape's content.
  return genericError(appCopy);
}

/**
 * `guard` is a required parameter, not an optional one, and that is the
 * point: there is no way to call this helper without deciding what the
 * response must look like, so a future endpoint cannot be added with its
 * body left unvalidated by omission.
 *
 * `appCopy` defaults to the pt-BR table so existing callers/tests keep
 * behaving unchanged; `GuidedFlow` passes its resolved `useCopy()` value
 * explicitly so a failure surfaces in the locale currently active, without
 * this module ever reading locale/storage itself (T21 fourth slice / #29).
 */
async function requestJson<T>(
  path: string,
  guard: ResponseGuard<T>,
  init?: RequestInit,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, error: genericError(appCopy) };
  }

  if (!response.ok) {
    return { ok: false, status: response.status, error: await toDisplayError(response, appCopy) };
  }

  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    return { ok: false, status: response.status, error: genericError(appCopy) };
  }

  if (!guard(parsed)) {
    // A 200 that does not satisfy its contract. `status` stays the real
    // status rather than being rewritten to an error code -- the transport
    // genuinely did succeed, and misreporting it would hide the fact that
    // the upstream is serving a body this app cannot read. The error itself
    // says nothing about `parsed`.
    return { ok: false, status: response.status, error: genericError(appCopy) };
  }

  return { ok: true, data: parsed };
}

export function getHealth(appCopy: AppCopy = defaultCopy): Promise<ApiResult<HealthResponse>> {
  return requestJson("/api/health", isHealthResponse, undefined, appCopy);
}

export function getExamples(appCopy: AppCopy = defaultCopy): Promise<ApiResult<ExamplesResponse>> {
  return requestJson("/api/examples", isExamplesResponse, undefined, appCopy);
}

export function getDocumentTypes(
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<DocumentTypesResponse>> {
  return requestJson("/api/documents/types", isDocumentTypesResponse, undefined, appCopy);
}

export function previewDocument(
  form: FormData,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<DocumentPreviewResponse>> {
  return requestJson(
    "/api/documents/preview",
    isDocumentPreviewResponse,
    { method: "POST", body: form },
    appCopy,
  );
}

export function executeDocument(
  form: FormData,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<ExecuteResponse>> {
  return requestJson(
    "/api/documents/execute",
    isExecuteResponse,
    { method: "POST", body: form },
    appCopy,
  );
}

export function previewDisclosure(
  body: DisclosureRequestBody,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<PreviewResponse>> {
  return requestJson(
    "/api/disclosure/preview",
    isPreviewResponse,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
    appCopy,
  );
}

export function executeDisclosure(
  body: DisclosureRequestBody,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<ExecuteResponse>> {
  return requestJson(
    "/api/disclosure/execute",
    isExecuteResponse,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
    appCopy,
  );
}

/**
 * Runs the same content through every B0-B4 strategy and returns all five
 * previews side by side -- never a provider call, for any of them (see
 * `application/contracts.py`'s `StrategyComparisonEntry` docstring). Takes
 * the same `DisclosureRequestBody` as `previewDisclosure`/`executeDisclosure`
 * -- the route ignores `body.strategy`, so callers reuse `buildRequestBody`
 * unchanged rather than needing a second, comparison-specific body shape.
 */
export function compareStrategies(
  body: DisclosureRequestBody,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<CompareResponse>> {
  return requestJson(
    "/api/disclosure/compare",
    isCompareResponse,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
    appCopy,
  );
}

/**
 * T27/T28 (issues #69-#70). Whether the export/restore UI should render at
 * all -- a UX convenience only, never a security decision: the route
 * handlers this app calls for the actual export/restore requests
 * (`exportDocument`/`restoreText` below) re-check the same server-side gate
 * independently, per request, regardless of what this call last reported.
 * A failure here (including an invalid body) is therefore always safe to
 * treat as "disabled" -- see `GuidedFlow`, which does exactly that.
 */
export function getDemoFeatures(
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<DemoFeaturesResponse>> {
  return requestJson("/api/demo/features", isDemoFeaturesResponse, undefined, appCopy);
}

/**
 * T28 / issue #70. Upload-only, mirroring T26's HTTP export route itself
 * (`POST /documents/export` takes the same multipart document shape as
 * `/documents/preview` -- no plain-text/example variant, and no
 * confirmation token). `lib/flow.ts`'s `buildDocumentFormData` builds the
 * exact same `FormData` this call needs, reused unchanged.
 */
export function exportDocument(
  form: FormData,
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<ExportResponse>> {
  return requestJson(
    "/api/documents/export",
    isExportResponse,
    { method: "POST", body: form },
    appCopy,
  );
}

/**
 * T28 / issue #70. `body.restore_handle` is the opaque handle
 * `exportDocument` returned; `body.text` is whatever the caller pasted or
 * imported (e.g. a simulated external response containing pseudonym-shaped
 * tokens). Neither this function nor anything it calls ever inspects,
 * decodes, or logs the handle -- it is forwarded to the proxy route
 * byte-identical, exactly like every other request body in this module.
 */
export function restoreText(
  body: { text: string; restore_handle: string },
  appCopy: AppCopy = defaultCopy,
): Promise<ApiResult<RestoreResponse>> {
  return requestJson(
    "/api/documents/restore",
    isRestoreResponse,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
    appCopy,
  );
}
