/**
 * Typed client over this app's own `/api/**` proxy routes (never the Python
 * API directly -- see `lib/proxy.ts`'s module docstring for the topology).
 * Thin wrappers only: no business logic, no retries. Every call returns a
 * discriminated `ApiResult<T>` so screens branch on `.ok` instead of
 * handling a raw `Response`/thrown error.
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
 */

import type {
  DisclosureRequestBody,
  ExamplesResponse,
  ExecuteResponse,
  HealthResponse,
  PreviewResponse,
} from "./contracts";
import { copy } from "./copy";

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

function genericError(): DisplayError {
  return { message: copy.errors.generic, kind: null, fields: null };
}

async function toDisplayError(response: Response): Promise<DisplayError> {
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    return genericError();
  }

  if (response.status === 422 && isValidationErrorResponseShape(parsed)) {
    return {
      message: copy.errors.validationFailed,
      kind: null,
      fields: parsed.detail.map((item) => ({ loc: item.loc, type: item.type })),
    };
  }

  if (isErrorResponseShape(parsed)) {
    return { message: parsed.detail, kind: parsed.kind, fields: null };
  }

  // Parsed fine but matches neither contract this app trusts -- fail
  // closed rather than displaying an unrecognized shape's content.
  return genericError();
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, error: genericError() };
  }

  if (!response.ok) {
    return { ok: false, status: response.status, error: await toDisplayError(response) };
  }

  try {
    const data = (await response.json()) as T;
    return { ok: true, data };
  } catch {
    return { ok: false, status: response.status, error: genericError() };
  }
}

export function getHealth(): Promise<ApiResult<HealthResponse>> {
  return requestJson<HealthResponse>("/api/health");
}

export function getExamples(): Promise<ApiResult<ExamplesResponse>> {
  return requestJson<ExamplesResponse>("/api/examples");
}

export function previewDisclosure(body: DisclosureRequestBody): Promise<ApiResult<PreviewResponse>> {
  return requestJson<PreviewResponse>("/api/disclosure/preview", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function executeDisclosure(body: DisclosureRequestBody): Promise<ApiResult<ExecuteResponse>> {
  return requestJson<ExecuteResponse>("/api/disclosure/execute", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
