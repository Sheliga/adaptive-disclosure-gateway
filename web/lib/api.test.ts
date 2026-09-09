import { afterEach, describe, expect, it, vi } from "vitest";

import { executeDisclosure, getExamples, getHealth, previewDisclosure } from "./api";
import { copy } from "./copy";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getHealth / getExamples — success", () => {
  it("returns ok:true with the parsed body on 200", async () => {
    const payload = { status: "ok", contract_version: "t20-application-api-v1" };
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
