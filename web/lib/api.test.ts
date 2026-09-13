import { afterEach, describe, expect, it, vi } from "vitest";

import { compareStrategies, executeDisclosure, getExamples, getHealth, previewDisclosure } from "./api";
import { CONTRACT_VERSION } from "./contracts";
import type {
  CategoryDisclosureSummary,
  CompareResponse,
  ExamplesResponse,
  ExecuteResponse,
  HealthResponse,
  PreviewResponse,
} from "./contracts";
import { copy } from "./copy";

/**
 * Fixtures below are COMPLETE, contract-faithful bodies -- every field
 * `application/wire.py` declares, with the type it declares. That is
 * deliberate: the point of these tests is that an incomplete body is
 * rejected, so a fixture that is itself incomplete would silently stop
 * testing anything.
 */

function healthBody(): HealthResponse {
  return {
    status: "ok",
    contract_version: CONTRACT_VERSION,
    provider: {
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      deterministic_demo_mode: true,
    },
    treatments_available: ["b0", "b1", "b2", "b3", "b4"],
  };
}

function examplesBody(): ExamplesResponse {
  return {
    contract_version: CONTRACT_VERSION,
    examples: [
      {
        example_id: "hr_team_summary_001",
        title: "hr_team_summary_001",
        domain: "hr",
        purpose: "team_summary",
        task: "Resuma a equipe.",
        character_count: 400,
      },
    ],
  };
}

function categoryBody(
  overrides: Partial<CategoryDisclosureSummary> = {},
): CategoryDisclosureSummary {
  return {
    category: "employee_name",
    outcome: "pseudonymized",
    action: "pseudonymize",
    crosses_trust_boundary: true,
    occurrence_count: 1,
    required_for_task: null,
    technical_reason: "policy hr-v1 rule",
    policy_version: "hr-v1",
    policy_restricted: null,
    impossible_under_policy: null,
    ...overrides,
  };
}

function previewBody(): PreviewResponse {
  return {
    contract_version: CONTRACT_VERSION,
    summary: {
      status: "allowed",
      categories: [categoryBody()],
      detected_span_count: 1,
      detected_categories: ["employee_name"],
    },
    external_payload: "conteudo transformado",
    payload_byte_count: 21,
    treatment: "b4",
    strategy: "recommended",
    governance: {
      domain: "hr",
      purpose: "team_summary",
      policy_version: "hr-v1",
      provider_class: "FakeProvider",
      requester_role: null,
      requested_pseudonym_scope: "session",
    },
    provider_mode: { provider_class: "FakeProvider" },
    inspection: null,
  };
}

function executeBody(): ExecuteResponse {
  return {
    contract_version: CONTRACT_VERSION,
    status: "allowed",
    summary: previewBody().summary,
    final_answer: "Resposta final reconstruída localmente.",
    provider: {
      called: true,
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      decoding_config: null,
      transmitted_bytes: 21,
      response_hash: "hash",
      failed: false,
      failure_kind: null,
    },
    reconstruction: {
      attempted: true,
      reconstructed_hash: "hash2",
      changed_from_provider_response: false,
    },
    treatment: "b4",
    strategy: "recommended",
    governance: previewBody().governance,
    total_ms: 42,
  };
}

function compareBody(): CompareResponse {
  return {
    contract_version: CONTRACT_VERSION,
    entries: [
      {
        strategy: "b0",
        treatment: "b0",
        recommended: false,
        unsafe_control_baseline: true,
        summary: {
          status: "allowed",
          categories: [categoryBody({ outcome: "preserved", action: "preserve", crosses_trust_boundary: true })],
          detected_span_count: 1,
          detected_categories: ["employee_name"],
        },
        external_payload: "conteudo original sem protecao",
        payload_byte_count: 30,
      },
      {
        strategy: "b1",
        treatment: "b1",
        recommended: false,
        unsafe_control_baseline: false,
        summary: previewBody().summary,
        external_payload: "conteudo b1",
        payload_byte_count: 20,
      },
      {
        strategy: "b2",
        treatment: "b2",
        recommended: false,
        unsafe_control_baseline: false,
        summary: previewBody().summary,
        external_payload: "conteudo b2",
        payload_byte_count: 20,
      },
      {
        strategy: "b3",
        treatment: "b3",
        recommended: false,
        unsafe_control_baseline: false,
        summary: previewBody().summary,
        external_payload: "conteudo b3",
        payload_byte_count: 20,
      },
      {
        strategy: "b4",
        treatment: "b4",
        recommended: true,
        unsafe_control_baseline: false,
        summary: previewBody().summary,
        external_payload: "conteudo transformado",
        payload_byte_count: 21,
      },
    ],
    governance: previewBody().governance,
    provider_mode: { provider_class: "FakeProvider" },
  };
}

/**
 * A loose, deliberately-mutable view of a decoded body. Corrupting a
 * fixture goes through this rather than through the real contract type --
 * the whole point is to build a body the contract type FORBIDS, which a
 * correctly-typed draft could not express.
 */
interface Draft {
  [key: string]: unknown;
}

function draftOf(body: object): Draft {
  return JSON.parse(JSON.stringify(body)) as Draft;
}

function nested(draft: Draft, key: string): Draft {
  return draft[key] as Draft;
}

function firstCategory(draft: Draft): Draft {
  return (nested(draft, "summary")["categories"] as Draft[])[0];
}

function firstEntry(draft: Draft): Draft {
  return (draft["entries"] as Draft[])[0];
}

function stub200(body: unknown): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getHealth / getExamples — success", () => {
  it("returns ok:true with the parsed body on a 200 that satisfies the whole contract", async () => {
    const payload = healthBody();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 })),
    );

    const result = await getHealth();

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(payload);
    }
  });

  it("rejects a 200 /health body missing the provider block the UI reads", async () => {
    // Regression: this partial body used to be accepted as `ok: true`, which
    // let `health.provider.deterministic_demo_mode` be read off `undefined`.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "ok", contract_version: CONTRACT_VERSION }), {
          status: 200,
        }),
      ),
    );

    const result = await getHealth();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });

  it("returns ok:true for a fully valid /examples body", async () => {
    const payload = examplesBody();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 })),
    );

    const result = await getExamples();

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(payload);
    }
  });

  it("calls the local proxy route, never the upstream API directly", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await getExamples();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/examples");
  });
});

describe("previewDisclosure / executeDisclosure — request shape", () => {
  it("POSTs the body as JSON to the local proxy route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await previewDisclosure({ text: "hello", task: "summarize" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/disclosure/preview");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "hello", task: "summarize" });
  });

  it("posts to the execute proxy route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await executeDisclosure({ text: "hello", task: "summarize" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/disclosure/execute");
  });
});

describe("error mapping — trusted contracts pass through", () => {
  it("maps a 400 ErrorResponse {detail, kind} to a DisplayError verbatim", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "missing task", kind: "MissingTaskError" }), {
          status: 400,
        }),
      ),
    );

    const result = await getHealth();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(400);
      expect(result.error).toEqual({ message: "missing task", kind: "MissingTaskError", fields: null });
    }
  });

  it("maps a 404 ExampleNotFoundError the same way", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "unknown example id", kind: "ExampleNotFoundError" }), {
          status: 404,
        }),
      ),
    );

    const result = await getExamples();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe("ExampleNotFoundError");
    }
  });

  it("maps a 422 ValidationErrorResponse to a safe generic message plus structured fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [{ loc: ["body", "text"], type: "string_type", msg: "request body failed validation" }],
          }),
          { status: 422 },
        ),
      ),
    );

    const result = await previewDisclosure({});

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(422);
      expect(result.error.message).toBe(copy.errors.validationFailed);
      expect(result.error.fields).toEqual([{ loc: ["body", "text"], type: "string_type" }]);
    }
  });

  it("maps a 502 from our own proxy (upstream unreachable) using the same ErrorResponse path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "an unexpected error occurred", kind: "UpstreamUnreachable" }),
          { status: 502 },
        ),
      ),
    );

    const result = await getHealth();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(502);
      expect(result.error.kind).toBe("UpstreamUnreachable");
    }
  });
});

describe("error mapping — fails closed on anything unrecognized", () => {
  it("falls back to a generic safe message when the body is not JSON at all", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>raw upstream prose, a stack trace, whatever</html>", { status: 500 })),
    );

    const result = await getHealth();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
      expect(result.error.message).not.toContain("raw upstream prose");
      expect(result.error.kind).toBeNull();
    }
  });

  it("falls back to a generic safe message when JSON parses but matches neither known contract", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ surprising: "shape", raw_document_fragment: "leaked?" }), {
          status: 500,
        }),
      ),
    );

    const result = await getExamples();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
      expect(JSON.stringify(result.error)).not.toContain("leaked?");
    }
  });

  it("falls back to a generic safe message when fetch itself throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network is down")));

    const result = await getHealth();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });
});

/**
 * The 200-response contract gate.
 *
 * These are the regressions for the defect this suite previously had no
 * coverage for: `requestJson` used to end in `(await response.json()) as T`,
 * a compile-time-only assertion. Any JSON body that happened to arrive with
 * a 200 reached the React tree wearing the contract's type, so a MISSING
 * field read as `undefined` -- and `undefined` is falsy, which is the exact
 * direction that turns "this crossed the trust boundary" into "this stayed
 * local" in `ReviewScreen`'s split.
 *
 * Every case below is a 200. The status code is never the thing under test;
 * the body's structure is.
 */
describe("200 response validation — preview fails closed on a broken contract", () => {
  it("accepts a preview body that satisfies the whole contract", async () => {
    const body = previewBody();
    stub200(body);

    const result = await previewDisclosure({ text: "x" });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(body);
    }
  });

  it("rejects a 200 whose category is MISSING crosses_trust_boundary", async () => {
    // The dangerous direction: absent reads as `undefined`, which is falsy,
    // so the review screen would file this category under "stays local".
    const draft = draftOf(previewBody());
    delete firstCategory(draft)["crosses_trust_boundary"];
    stub200(draft);

    const result = await previewDisclosure({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });

  it("rejects a 200 whose crosses_trust_boundary is the STRING \"false\"", async () => {
    // The opposite direction, equally wrong: a truthy string would file a
    // local-only category under "was sent to the provider". Either way the
    // UI must not guess -- only a real boolean is the authoritative flag.
    const draft = draftOf(previewBody());
    firstCategory(draft)["crosses_trust_boundary"] = "false";
    stub200(draft);

    const result = await previewDisclosure({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });

  it("rejects a 200 whose crosses_trust_boundary is the STRING \"true\"", async () => {
    const draft = draftOf(previewBody());
    firstCategory(draft)["crosses_trust_boundary"] = "true";
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose summary.status is a value this UI does not know", async () => {
    // `status` gates the confirm button. Anything that is not exactly
    // "allowed" or "blocked" must never be treated as permission to send:
    // an unknown status is not `blocked`, so `isBlocked` would be false and
    // the confirm-and-send button would render.
    const draft = draftOf(previewBody());
    nested(draft, "summary")["status"] = "partially_allowed";
    stub200(draft);

    const result = await previewDisclosure({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });

  it("rejects a 200 whose summary.status is missing entirely", async () => {
    const draft = draftOf(previewBody());
    delete nested(draft, "summary")["status"];
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("still accepts a blocked summary — blocked is a valid contract state", async () => {
    const draft = draftOf(previewBody());
    nested(draft, "summary")["status"] = "blocked";
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(true);
  });

  it("rejects a 200 whose summary.categories is not an array", async () => {
    const draft = draftOf(previewBody());
    nested(draft, "summary")["categories"] = { employee_name: "pseudonymized" };
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose summary is missing altogether", async () => {
    const draft = draftOf(previewBody());
    delete draft["summary"];
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose category is missing its outcome", async () => {
    const draft = draftOf(previewBody());
    delete firstCategory(draft)["outcome"];
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose external_payload is not a string", async () => {
    const draft = draftOf(previewBody());
    draft["external_payload"] = { redacted: true };
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose payload_byte_count is not a number", async () => {
    const draft = draftOf(previewBody());
    draft["payload_byte_count"] = "21";
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 carrying a contract_version this UI was not written against", async () => {
    const draft = draftOf(previewBody());
    draft["contract_version"] = "t99-some-future-contract";
    stub200(draft);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 that is a JSON array rather than an object", async () => {
    stub200([previewBody()]);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 that is JSON null", async () => {
    stub200(null);

    expect((await previewDisclosure({ text: "x" })).ok).toBe(false);
  });
});

describe("200 response validation — execute fails closed on a broken contract", () => {
  it("accepts an execute body that satisfies the whole contract", async () => {
    const body = executeBody();
    stub200(body);

    const result = await executeDisclosure({ text: "x" });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(body);
    }
  });

  it("rejects a 200 whose provider block is missing", async () => {
    // `ResultScreen` reads `execute.provider.failed` unconditionally.
    const draft = draftOf(executeBody());
    delete draft["provider"];
    stub200(draft);

    const result = await executeDisclosure({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });

  it("rejects a 200 whose provider.failed is missing", async () => {
    // Absent reads as `undefined` -> falsy -> "the provider call succeeded",
    // and the screen would render `final_answer` as a real completion.
    const draft = draftOf(executeBody());
    delete nested(draft, "provider")["failed"];
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose provider.failed is the STRING \"false\"", async () => {
    const draft = draftOf(executeBody());
    nested(draft, "provider")["failed"] = "false";
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose provider.failure_kind is neither a string nor null", async () => {
    const draft = draftOf(executeBody());
    nested(draft, "provider")["failure_kind"] = { code: 500 };
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose final_answer is neither a string nor null", async () => {
    const draft = draftOf(executeBody());
    draft["final_answer"] = { text: "answer" };
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("accepts final_answer: null — the contract's own blocked/failed shape", async () => {
    const draft = draftOf(executeBody());
    draft["final_answer"] = null;
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(true);
  });

  it("rejects a 200 whose summary.status is unknown", async () => {
    const draft = draftOf(executeBody());
    nested(draft, "summary")["status"] = "maybe";
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose reconstruction block is missing", async () => {
    const draft = draftOf(executeBody());
    delete draft["reconstruction"];
    stub200(draft);

    expect((await executeDisclosure({ text: "x" })).ok).toBe(false);
  });
});

describe("200 response validation — nothing from the rejected body is echoed", () => {
  it("shows only the generic message, never a fragment of the invalid response", async () => {
    // The no-leak invariant applied to this boundary: a body we refused to
    // understand may still contain document text, so the failure it maps to
    // must carry NONE of it -- not in the message, not in `kind`, not in
    // `fields`.
    const draft = draftOf(previewBody());
    delete firstCategory(draft)["crosses_trust_boundary"];
    draft["external_payload"] = "CPF 123.456.789-00 de Maria Oliveira";
    stub200(draft);

    const result = await previewDisclosure({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toEqual({ message: copy.errors.generic, kind: null, fields: null });
      const serialized = JSON.stringify(result.error);
      expect(serialized).not.toContain("123.456.789-00");
      expect(serialized).not.toContain("Maria Oliveira");
      expect(serialized).not.toContain("crosses_trust_boundary");
      expect(serialized).not.toContain("external_payload");
    }
  });

  it("does not echo an invalid execute body's final_answer either", async () => {
    const draft = draftOf(executeBody());
    delete nested(draft, "provider")["failed"];
    draft["final_answer"] = "resposta contendo Maria Oliveira";
    stub200(draft);

    const result = await executeDisclosure({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(JSON.stringify(result.error)).not.toContain("Maria Oliveira");
    }
  });
});

describe("previewDisclosure / executeDisclosure / compareStrategies — request shape", () => {
  it("posts to the compare proxy route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await compareStrategies({ text: "hello", task: "summarize" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/disclosure/compare");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "hello", task: "summarize" });
  });
});

describe("200 response validation — compare fails closed on a broken contract", () => {
  it("accepts a compare body that satisfies the whole contract", async () => {
    const body = compareBody();
    stub200(body);

    const result = await compareStrategies({ text: "x" });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(body);
    }
  });

  it("rejects a 200 whose entries is not an array", async () => {
    const draft = draftOf(compareBody());
    draft["entries"] = { b0: {} };
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry is missing strategy", async () => {
    const draft = draftOf(compareBody());
    delete firstEntry(draft)["strategy"];
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry is missing recommended", async () => {
    const draft = draftOf(compareBody());
    delete firstEntry(draft)["recommended"];
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry is MISSING unsafe_control_baseline", async () => {
    // Absent reads as `undefined` -> falsy -> the B0 warning would never
    // render for an entry that omitted the flag.
    const draft = draftOf(compareBody());
    delete firstEntry(draft)["unsafe_control_baseline"];
    stub200(draft);

    const result = await compareStrategies({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.message).toBe(copy.errors.generic);
    }
  });

  it('rejects a 200 whose unsafe_control_baseline is the STRING "false"', async () => {
    // The opposite direction, equally wrong: a truthy string would light up
    // the B0 warning on an entry that is not the unsafe control.
    const draft = draftOf(compareBody());
    firstEntry(draft)["unsafe_control_baseline"] = "false";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it('rejects a 200 whose unsafe_control_baseline is the STRING "true"', async () => {
    const draft = draftOf(compareBody());
    firstEntry(draft)["unsafe_control_baseline"] = "true";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry's crosses_trust_boundary is not a real boolean", async () => {
    const draft = draftOf(compareBody());
    (nested(firstEntry(draft), "summary")["categories"] as Draft[])[0]["crosses_trust_boundary"] = "true";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry's summary.status is unknown", async () => {
    const draft = draftOf(compareBody());
    nested(firstEntry(draft), "summary")["status"] = "maybe";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry's external_payload is not a string", async () => {
    const draft = draftOf(compareBody());
    firstEntry(draft)["external_payload"] = { redacted: true };
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose entry's payload_byte_count is not a number", async () => {
    const draft = draftOf(compareBody());
    firstEntry(draft)["payload_byte_count"] = "30";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 whose governance block is missing", async () => {
    const draft = draftOf(compareBody());
    delete draft["governance"];
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a 200 carrying a contract_version this UI was not written against", async () => {
    const draft = draftOf(compareBody());
    draft["contract_version"] = "t99-some-future-contract";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("does not echo the rejected body's payload or field names in the error", async () => {
    const draft = draftOf(compareBody());
    delete firstEntry(draft)["unsafe_control_baseline"];
    firstEntry(draft)["external_payload"] = "CPF 123.456.789-00 de Maria Oliveira";
    stub200(draft);

    const result = await compareStrategies({ text: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toEqual({ message: copy.errors.generic, kind: null, fields: null });
      const serialized = JSON.stringify(result.error);
      expect(serialized).not.toContain("123.456.789-00");
      expect(serialized).not.toContain("Maria Oliveira");
      expect(serialized).not.toContain("unsafe_control_baseline");
      expect(serialized).not.toContain("external_payload");
    }
  });
});

describe("200 response validation — compare requires exactly the canonical B0-B4 order", () => {
  // These pin the T21/#49 hardening: a `CompareResponse` is accepted only
  // when `entries` is exactly the five canonical strategies, in canonical
  // order, each with the treatment code the real wire emits for it. Count,
  // order, duplicates and unknown codes are all folded into the single
  // position-against-`CANONICAL_COMPARISON_ORDER` check in
  // `isCompareResponse` -- these tests exercise each failure mode that
  // check is meant to catch.

  it("accepts a body with exactly b0, b1, b2, b3, b4 in canonical order", async () => {
    const body = compareBody();
    stub200(body);

    const result = await compareStrategies({ text: "x" });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.entries.map((e) => e.strategy)).toEqual(["b0", "b1", "b2", "b3", "b4"]);
    }
  });

  it("rejects a body with only four entries", async () => {
    const draft = draftOf(compareBody());
    (draft["entries"] as unknown[]).pop();
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a body with six entries (an extra, valid-looking sixth entry appended)", async () => {
    const draft = draftOf(compareBody());
    const entries = draft["entries"] as Draft[];
    entries.push(JSON.parse(JSON.stringify(entries[4])));
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a body with an empty entries array", async () => {
    const draft = draftOf(compareBody());
    draft["entries"] = [];
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a body whose entries are out of canonical order (b0, b2, b1, b3, b4)", async () => {
    const draft = draftOf(compareBody());
    const entries = draft["entries"] as Draft[];
    [entries[1], entries[2]] = [entries[2], entries[1]];
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a body with a duplicated strategy (b0 repeated in place of b1)", async () => {
    const draft = draftOf(compareBody());
    const entries = draft["entries"] as Draft[];
    entries[1] = JSON.parse(JSON.stringify(entries[0]));
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it.each(["b5", "recommended", "banana"])(
    "rejects a body with an unknown strategy code %j at position 0",
    async (badStrategy) => {
      const draft = draftOf(compareBody());
      firstEntry(draft)["strategy"] = badStrategy;
      stub200(draft);

      expect((await compareStrategies({ text: "x" })).ok).toBe(false);
    },
  );

  it("rejects a body with an unknown treatment code", async () => {
    const draft = draftOf(compareBody());
    firstEntry(draft)["treatment"] = "banana";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });

  it("rejects a body whose treatment does not match its entry's strategy/position (b1 entry carrying b2's treatment)", async () => {
    const draft = draftOf(compareBody());
    (draft["entries"] as Draft[])[1]["treatment"] = "b2";
    stub200(draft);

    expect((await compareStrategies({ text: "x" })).ok).toBe(false);
  });
});

describe("200 response validation — examples and health", () => {
  it("rejects a 200 /examples whose examples is not an array", async () => {
    stub200({ contract_version: CONTRACT_VERSION, examples: { a: 1 } });

    expect((await getExamples()).ok).toBe(false);
  });

  it("rejects a 200 /examples whose entry is missing example_id", async () => {
    const draft = draftOf(examplesBody());
    delete (draft["examples"] as Draft[])[0]["example_id"];
    stub200(draft);

    expect((await getExamples()).ok).toBe(false);
  });

  it("rejects a 200 /health whose deterministic_demo_mode is not a boolean", async () => {
    // Fail-closed on the FakeProvider label specifically: a non-boolean must
    // not be coerced into "this is a real provider" OR "this is the demo".
    const draft = draftOf(healthBody());
    nested(draft, "provider")["deterministic_demo_mode"] = "true";
    stub200(draft);

    expect((await getHealth()).ok).toBe(false);
  });

  it("rejects a 200 /health whose treatments_available is not a string array", async () => {
    const draft = draftOf(healthBody());
    draft["treatments_available"] = [0, 1, 2, 3, 4];
    stub200(draft);

    expect((await getHealth()).ok).toBe(false);
  });
});
