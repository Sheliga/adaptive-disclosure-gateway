import { describe, expect, it } from "vitest";

import { buildDocumentFormData, isSupportedUploadFilename, type ComposeState } from "./flow";

function uploadedCompose(file: File): ComposeState {
  return {
    mode: "upload",
    exampleId: null,
    pastedText: "",
    file: {
      file,
      filename: file.name,
      byteSize: file.size,
      displayType: "PDF",
    },
    fileError: null,
    task: "Quais são as obrigações?",
    documentType: "contract",
    analysisMode: "contract_summary",
  };
}

describe("structured document upload request", () => {
  it.each(["contract.pdf", "contract.docx", "notes.txt", "notes.md"])(
    "accepts %s client-side",
    (filename) => expect(isSupportedUploadFilename(filename)).toBe(true),
  );

  it("rejects an unsupported extension", () => {
    expect(isSupportedUploadFilename("contract.png")).toBe(false);
  });

  it("builds multipart preview data from the original File without governance fields", () => {
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "contract.pdf", {
      type: "application/pdf",
    });
    const form = buildDocumentFormData(uploadedCompose(file));

    expect(form.get("file")).toBe(file);
    expect(form.get("task")).toBe("Quais são as obrigações?");
    expect(form.get("document_type")).toBe("contract");
    expect(form.get("analysis_mode")).toBe("contract_summary");
    for (const forbidden of ["governance", "domain", "policy_version", "provider_class", "requester_role"]) {
      expect(form.has(forbidden)).toBe(false);
    }
  });

  it("adds exactly the opaque confirmation token for execute", () => {
    const file = new File(["synthetic"], "contract.docx");
    const form = buildDocumentFormData(uploadedCompose(file), "opaque.preview.token");

    expect(form.get("file")).toBe(file);
    expect(form.get("confirmation_token")).toBe("opaque.preview.token");
  });
});
