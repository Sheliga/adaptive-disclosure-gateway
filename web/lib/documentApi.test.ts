import { afterEach, describe, expect, it, vi } from "vitest";

import { executeDocument, getDocumentTypes, previewDocument } from "./api";
import { CONTRACT_VERSION, type DocumentPreviewResponse, type ExecuteResponse } from "./contracts";

const summary = {
  status: "allowed" as const,
  categories: [],
  detected_span_count: 0,
  detected_categories: [],
};
const governance = {
  domain: "contracts",
  purpose: "contract_summary",
  policy_version: "contracts-v1",
  provider_class: "FakeProvider",
  requester_role: "contract_analyst",
  requested_pseudonym_scope: "session",
};

function preview(): DocumentPreviewResponse {
  return {
    contract_version: CONTRACT_VERSION,
    summary,
    external_payload: "safe",
    payload_byte_count: 4,
    treatment: "b4",
    strategy: "recommended",
    governance,
    provider_mode: { provider_class: "FakeProvider" },
    confirmation_token: "opaque",
  };
}

function execute(): ExecuteResponse {
  return {
    contract_version: CONTRACT_VERSION,
    status: "allowed",
    summary,
    final_answer: "answer",
    provider: {
      called: true,
      provider_class: "FakeProvider",
      model_id: "fake",
      model_snapshot: null,
      decoding_config: null,
      transmitted_bytes: 4,
      response_hash: null,
      failed: false,
      failure_kind: null,
    },
    reconstruction: {
      attempted: true,
      reconstructed_hash: null,
      changed_from_provider_response: false,
    },
    treatment: "b4",
    strategy: "recommended",
    governance,
    total_ms: 1,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("document API client", () => {
  it("discovers document vocabulary from /api/documents/types", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        contract_version: CONTRACT_VERSION,
        document_types: [
          {
            document_type: "contract",
            analysis_modes: ["contract_summary"],
            default_analysis_mode: "contract_summary",
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    expect((await getDocumentTypes()).ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith("/api/documents/types", undefined);
  });

  it("posts FormData for preview without setting multipart Content-Type manually", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(preview()));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();

    expect((await previewDocument(form)).ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/documents/preview",
      expect.objectContaining({ method: "POST", body: form }),
    );
    expect(fetchMock.mock.calls[0][1].headers).toBeUndefined();
  });

  it("posts the confirmed FormData to execute", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(execute()));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();

    expect((await executeDocument(form)).ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/documents/execute",
      expect.objectContaining({ method: "POST", body: form }),
    );
  });
});
