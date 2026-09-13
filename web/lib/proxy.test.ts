import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { proxyGet, proxyJsonPost, proxyMultipartPost } from "./proxy";

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  process.env.ADG_API_BASE_URL = "http://upstream.test";
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  process.env = { ...ORIGINAL_ENV };
});

describe("proxyGet", () => {
  it("forwards to <ADG_API_BASE_URL><path> and mirrors a 200 body byte-identically", async () => {
    const upstreamBody = JSON.stringify({ status: "ok", nested: { a: 1 } });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(upstreamBody, {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await proxyGet("/health");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://upstream.test/health");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("GET");

    expect(response.status).toBe(200);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("mirrors a non-2xx upstream status and body unchanged (400)", async () => {
    const upstreamBody = JSON.stringify({ detail: "bad request text", kind: "IngestionError" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const response = await proxyGet("/examples");

    expect(response.status).toBe(400);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("falls back to the default base URL when ADG_API_BASE_URL is unset", async () => {
    delete process.env.ADG_API_BASE_URL;
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await proxyGet("/health");

    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8000/health");
  });

  it("returns a fixed 502 with no exception detail when upstream is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED 127.0.0.1:8000 -- secret internal detail")),
    );

    const response = await proxyGet("/health");

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body).toEqual({ detail: "an unexpected error occurred", kind: "UpstreamUnreachable" });
    const bodyText = JSON.stringify(body);
    expect(bodyText).not.toContain("ECONNREFUSED");
    expect(bodyText).not.toContain("secret internal detail");
  });
});

describe("proxyMultipartPost", () => {
  it("forwards the original body stream and multipart boundary without parsing it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const boundary = "----synthetic-boundary";
    const incoming = new Request("http://web.test/api/documents/preview", {
      method: "POST",
      headers: { "content-type": `multipart/form-data; boundary=${boundary}` },
      body: `--${boundary}\r\nsynthetic multipart bytes\r\n--${boundary}--`,
    });
    const originalBody = incoming.body;

    await proxyMultipartPost("/documents/preview", incoming);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://upstream.test/documents/preview",
      expect.objectContaining({
        method: "POST",
        body: originalBody,
        duplex: "half",
        headers: { "content-type": `multipart/form-data; boundary=${boundary}` },
      }),
    );
  });
});

describe("proxyJsonPost", () => {
  it("forwards the request body upstream byte-identical to what came in", async () => {
    const requestBody = JSON.stringify({ text: "confidential document text", task: "summarize" });
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const incoming = new Request("http://web.test/api/disclosure/preview", {
      method: "POST",
      body: requestBody,
    });

    await proxyJsonPost("/disclosure/preview", incoming);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://upstream.test/disclosure/preview");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(requestBody);
  });

  it("mirrors upstream status and body byte-identically for a 422 validation error", async () => {
    const upstreamBody = JSON.stringify({
      detail: [{ loc: ["body", "text"], type: "string_type", msg: "request body failed validation" }],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const incoming = new Request("http://web.test/api/disclosure/preview", {
      method: "POST",
      body: "{}",
    });
    const response = await proxyJsonPost("/disclosure/preview", incoming);

    expect(response.status).toBe(422);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("mirrors upstream status and body byte-identically for a 400", async () => {
    const upstreamBody = JSON.stringify({ detail: "missing task", kind: "MissingTaskError" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const incoming = new Request("http://web.test/api/disclosure/execute", {
      method: "POST",
      body: "{}",
    });
    const response = await proxyJsonPost("/disclosure/execute", incoming);

    expect(response.status).toBe(400);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("returns a fixed 502 with no exception detail when upstream is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("secret connection failure detail")));

    const incoming = new Request("http://web.test/api/disclosure/execute", {
      method: "POST",
      body: JSON.stringify({ text: "sensitive document contents" }),
    });
    const response = await proxyJsonPost("/disclosure/execute", incoming);

    expect(response.status).toBe(502);
    const bodyText = await response.text();
    expect(bodyText).not.toContain("secret connection failure detail");
    expect(bodyText).not.toContain("sensitive document contents");
    expect(JSON.parse(bodyText)).toEqual({
      detail: "an unexpected error occurred",
      kind: "UpstreamUnreachable",
    });
  });

  it("never logs the request or response body", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ final_answer: "very sensitive reconstructed answer" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const incoming = new Request("http://web.test/api/disclosure/execute", {
      method: "POST",
      body: JSON.stringify({ text: "very sensitive document body" }),
    });
    await proxyJsonPost("/disclosure/execute", incoming);

    expect(logSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
