import { afterEach, describe, expect, it, vi } from "vitest";

import { DEMO_TRANSPARENCY_ENV_VAR } from "@/lib/demoTransparency";

import { POST } from "./route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function jsonRequest(): Request {
  return new Request("http://web.test/api/documents/restore", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text: "PSEUDO-abc123", restore_handle: "opaque.handle" }),
  });
}

describe("POST /api/documents/restore -- gated behind ADG_ENABLE_DEMO_TRANSPARENCY", () => {
  const disabledValues: (string | undefined)[] = [undefined, "", " ", "0", "true", "yes", "2"];

  it.each(disabledValues)(
    "returns the fixed 404 and never calls fetch when the flag is %j",
    async (value) => {
      if (value === undefined) {
        delete process.env[DEMO_TRANSPARENCY_ENV_VAR];
      } else {
        process.env[DEMO_TRANSPARENCY_ENV_VAR] = value;
      }
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);

      const response = await POST(jsonRequest());

      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ detail: "not found", kind: "DemoTransparencyDisabled" });
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it.each(["1", " 1 "])(
    "forwards to upstream POST /documents/restore when the flag is %j",
    async (value) => {
      process.env[DEMO_TRANSPARENCY_ENV_VAR] = value;
      process.env.ADG_API_BASE_URL = "http://upstream.test";
      const requestBody = JSON.stringify({ text: "PSEUDO-abc123", restore_handle: "opaque.handle" });
      const upstreamBody = JSON.stringify({ contract_version: "t20-application-api-v1", ok: true });
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 200, headers: { "content-type": "application/json" } }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const request = new Request("http://web.test/api/documents/restore", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: requestBody,
      });
      const response = await POST(request);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("http://upstream.test/documents/restore");
      expect(init.body).toBe(requestBody);
      expect(response.status).toBe(200);
      expect(await response.text()).toBe(upstreamBody);
    },
  );

  it("mirrors an upstream 400 (RestoreHandleInvalidError) status and body unchanged", async () => {
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";
    const upstreamBody = JSON.stringify({ detail: "restore handle is invalid", kind: "RestoreHandleInvalidError" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 400, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(jsonRequest());

    expect(response.status).toBe(400);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("mirrors an upstream 400 (RestoreHandleExpiredError) status and body unchanged", async () => {
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";
    const upstreamBody = JSON.stringify({ detail: "restore handle has expired", kind: "RestoreHandleExpiredError" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 400, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(jsonRequest());

    expect(response.status).toBe(400);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("mirrors an upstream 503 (RestoreUnavailableError) status and body unchanged", async () => {
    process.env[DEMO_TRANSPARENCY_ENV_VAR] = "1";
    const upstreamBody = JSON.stringify({ detail: "restore is not available", kind: "RestoreUnavailableError" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 503, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(jsonRequest());

    expect(response.status).toBe(503);
    expect(await response.text()).toBe(upstreamBody);
  });

  it("public posture: inspection on, transparency/vault unset -> 404 and zero upstream calls", async () => {
    // The three demo capabilities are independent env-var gates; none may
    // ever be derived from another. This pins that a deployment which
    // enables ADG_ENABLE_DEMO_INSPECTION alone does not also, as a side
    // effect, open the restore proxy.
    process.env.ADG_ENABLE_DEMO_INSPECTION = "1";
    delete process.env[DEMO_TRANSPARENCY_ENV_VAR];
    delete process.env.ADG_ENABLE_DEMO_VAULT_EXPLORER;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(jsonRequest());

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ detail: "not found", kind: "DemoTransparencyDisabled" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
