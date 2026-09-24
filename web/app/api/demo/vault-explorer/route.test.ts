import { afterEach, describe, expect, it, vi } from "vitest";

import { DEMO_VAULT_EXPLORER_ENV_VAR } from "@/lib/demoVaultExplorer";

import { dynamic, POST } from "./route";

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function jsonRequest(body: unknown = { token: "vx1.opaque" }): Request {
  return new Request("http://web.test/api/demo/vault-explorer", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("route.ts declares the route segment config", () => {
  it("exports dynamic = force-dynamic", () => {
    expect(dynamic).toBe("force-dynamic");
  });
});

describe("POST /api/demo/vault-explorer -- gated behind ADG_ENABLE_DEMO_VAULT_EXPLORER", () => {
  const disabledValues: (string | undefined)[] = [undefined, "", " ", "0", "true", "yes", "2"];

  it.each(disabledValues)(
    "returns the fixed 404 with no-store headers and never calls fetch when the flag is %j",
    async (value) => {
      if (value === undefined) {
        delete process.env[DEMO_VAULT_EXPLORER_ENV_VAR];
      } else {
        process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = value;
      }
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);

      const response = await POST(jsonRequest());

      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ detail: "not found", kind: "DemoVaultExplorerDisabled" });
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(response.headers.get("pragma")).toBe("no-cache");
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it.each(["1", " 1 "])(
    "forwards to upstream POST /demo/vault-explorer when the flag is %j, body byte-identical",
    async (value) => {
      process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = value;
      process.env.ADG_API_BASE_URL = "http://upstream.test";
      const requestBody = JSON.stringify({ token: "vx1.opaque-token-value" });
      const upstreamBody = JSON.stringify({
        contract_version: "t20-application-api-v1",
        scope: "session",
        entry_count: 0,
        entries: [],
      });
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 200, headers: { "content-type": "application/json" } }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const request = new Request("http://web.test/api/demo/vault-explorer", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: requestBody,
      });
      const response = await POST(request);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("http://upstream.test/demo/vault-explorer");
      expect(init.body).toBe(requestBody);
      expect(response.status).toBe(200);
      expect(await response.text()).toBe(upstreamBody);
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(response.headers.get("pragma")).toBe("no-cache");
    },
  );

  it("mirrors an upstream 400 (VaultExplorerReferenceError) status and body unchanged, plus no-store headers", async () => {
    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";
    const upstreamBody = JSON.stringify({
      detail: "vault explorer reference is invalid, malformed, expired, or was not issued by this process",
      kind: "VaultExplorerReferenceError",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 400, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(jsonRequest());

    expect(response.status).toBe(400);
    expect(await response.text()).toBe(upstreamBody);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("pragma")).toBe("no-cache");
  });

  it("mirrors an upstream 404 (from the api itself disabled) status and body unchanged", async () => {
    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";
    const upstreamBody = JSON.stringify({ detail: "not found", kind: "DemoVaultExplorerDisabled" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 404, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(jsonRequest());

    expect(response.status).toBe(404);
    expect(await response.text()).toBe(upstreamBody);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("mirrors an upstream 422 validation error status and body unchanged", async () => {
    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";
    const upstreamBody = JSON.stringify({ detail: [{ loc: ["body", "token"], type: "missing", msg: "x" }] });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(upstreamBody, { status: 422, headers: { "content-type": "application/json" } }),
      ),
    );

    const response = await POST(jsonRequest({}));

    expect(response.status).toBe(422);
    expect(await response.text()).toBe(upstreamBody);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("never puts the token in the URL -- only ever in the forwarded JSON body", async () => {
    process.env[DEMO_VAULT_EXPLORER_ENV_VAR] = "1";
    process.env.ADG_API_BASE_URL = "http://upstream.test";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await POST(jsonRequest({ token: "vx1.SUPER_SECRET_TOKEN" }));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).not.toContain("SUPER_SECRET_TOKEN");
    expect(init.body).toContain("SUPER_SECRET_TOKEN");
  });

  it("public posture: inspection on, transparency/vault unset -> 404 and zero upstream calls", async () => {
    // The three demo capabilities are independent env-var gates; none may
    // ever be derived from another. This pins that a deployment which
    // enables ADG_ENABLE_DEMO_INSPECTION alone does not also, as a side
    // effect, open the vault explorer proxy.
    process.env.ADG_ENABLE_DEMO_INSPECTION = "1";
    delete process.env[DEMO_VAULT_EXPLORER_ENV_VAR];
    delete process.env.ADG_ENABLE_DEMO_TRANSPARENCY;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(jsonRequest());

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ detail: "not found", kind: "DemoVaultExplorerDisabled" });
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
