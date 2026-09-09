import { describe, expect, it } from "vitest";

import { describeCategory } from "./categoryLabels";
import { copy } from "./copy";

describe("describeCategory — the HR policy's categories read as pt-BR", () => {
  it.each([
    ["employee_name", "Nome do funcionário"],
    ["cpf", "CPF"],
    ["salary", "Salário"],
    ["department", "Departamento"],
    ["medical_data", "Dados médicos"],
  ])("maps %s to a human label", (identifier, expected) => {
    const descriptor = describeCategory(identifier);

    expect(descriptor.label).toBe(expected);
    expect(descriptor.known).toBe(true);
    expect(descriptor.technicalId).toBe(identifier);
  });

  it("covers every category the frozen HR policies can actually produce", () => {
    // `configs/policies/hr-v1|v2|v3.yaml` declare exactly these rules. A
    // category the demo can hit with no copy for it would render as
    // "não reconhecida" to the reviewer, which is safe but wrong.
    for (const identifier of ["employee_name", "cpf", "medical_data", "salary", "department"]) {
      expect(describeCategory(identifier).known).toBe(true);
    }
  });
});

describe("describeCategory — fails closed on anything it has no copy for", () => {
  it("does not invent a meaning for an unrecognized identifier", () => {
    const descriptor = describeCategory("bank_account");

    expect(descriptor.known).toBe(false);
    expect(descriptor.label).toBe(copy.categories.unrecognized);
    // The raw identifier survives as a technical detail so the reviewer can
    // report what they saw -- it is simply not the label.
    expect(descriptor.technicalId).toBe("bank_account");
  });

  it("never derives a label by prettifying the identifier itself", () => {
    // A "humanize the snake_case" fallback would be the tempting shortcut
    // and is exactly wrong here: it produces a confident-looking label for
    // a category this UI has never been reviewed against. `party_name`
    // would become "Party name", which reads as authoritative copy.
    const descriptor = describeCategory("party_name");

    expect(descriptor.known).toBe(false);
    expect(descriptor.label).not.toContain("party");
    expect(descriptor.label).not.toContain("Party");
  });

  it("treats an empty identifier as unrecognized rather than as a blank label", () => {
    expect(describeCategory("").known).toBe(false);
    expect(describeCategory("").label).toBe(copy.categories.unrecognized);
  });

  it("does not resolve inherited Object.prototype keys as categories", () => {
    // `copy.categories.labels` is a plain object literal, so a lookup of
    // "constructor"/"toString" would otherwise hit the prototype chain and
    // return a function, not a label.
    for (const inherited of ["constructor", "toString", "hasOwnProperty", "__proto__"]) {
      const descriptor = describeCategory(inherited);
      expect(descriptor.known).toBe(false);
      expect(descriptor.label).toBe(copy.categories.unrecognized);
    }
  });
});
