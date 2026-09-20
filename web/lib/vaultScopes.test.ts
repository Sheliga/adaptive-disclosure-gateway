import { describe, expect, it } from "vitest";

import { KNOWN_VAULT_SCOPES } from "./contracts";
import { copy } from "./copy";
import { describeVaultScope } from "./vaultScopes";

describe("describeVaultScope -- known scopes read as pt-BR", () => {
  it.each([
    ["request", "Uma única requisição"],
    ["document", "Um documento"],
    ["session", "Uma sessão"],
  ])("maps %s to a human label", (identifier, expected) => {
    const descriptor = describeVaultScope(identifier);

    expect(descriptor.label).toBe(expected);
    expect(descriptor.known).toBe(true);
    expect(descriptor.technicalId).toBe(identifier);
    expect(descriptor.explanation).not.toBeNull();
  });

  it("covers every scope KNOWN_VAULT_SCOPES declares", () => {
    for (const scope of KNOWN_VAULT_SCOPES) {
      expect(describeVaultScope(scope).known).toBe(true);
    }
  });
});

describe("describeVaultScope -- fails closed on anything it has no copy for", () => {
  it("does not invent a meaning for an unrecognized identifier, e.g. organization", () => {
    // "organization" is a real Python PseudonymScope member, but the
    // explorer never returns it (see KNOWN_VAULT_SCOPES's own docstring) --
    // this module still must not silently accept it as known if it ever
    // arrived anyway.
    const descriptor = describeVaultScope("organization");

    expect(descriptor.known).toBe(false);
    expect(descriptor.label).toBe(copy.vaultScopes.unrecognized);
    expect(descriptor.technicalId).toBe("organization");
    expect(descriptor.explanation).toBeNull();
  });

  it("never derives a label by prettifying the identifier itself", () => {
    const descriptor = describeVaultScope("unexpected_scope");

    expect(descriptor.known).toBe(false);
    expect(descriptor.label).not.toContain("unexpected");
    expect(descriptor.label).not.toContain("scope");
  });

  it("treats an empty identifier as unrecognized rather than as a blank label", () => {
    expect(describeVaultScope("").known).toBe(false);
    expect(describeVaultScope("").label).toBe(copy.vaultScopes.unrecognized);
  });

  it("does not resolve inherited Object.prototype keys as scopes", () => {
    for (const inherited of ["constructor", "toString", "hasOwnProperty", "__proto__"]) {
      const descriptor = describeVaultScope(inherited);
      expect(descriptor.known).toBe(false);
      expect(descriptor.label).toBe(copy.vaultScopes.unrecognized);
    }
  });
});
