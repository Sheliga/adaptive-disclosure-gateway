/**
 * T21 / issue #29: the example picker must not show a reviewer raw corpus
 * sample ids.
 *
 * `GET /examples` returns `title = sample_id` (see
 * `application/examples.py` -- the corpus schema has no human-authored
 * title, and the API deliberately returns identifiers rather than prose,
 * since the UI owns copy). Rendering that verbatim put
 * `hr_department_aggregation_001` in front of a prospective advisor, which
 * fails issue #29's own acceptance criterion that "a reviewer unfamiliar
 * with the project can understand the purpose without external
 * documentation".
 *
 * The label is therefore derived here, in the UI, from the example's
 * `purpose` -- a small, semantically meaningful, stable set -- with the raw
 * id demoted to an on-demand technical detail. An unmapped purpose falls
 * back to the raw id rather than inventing a label for something this
 * module does not actually recognize.
 */
import { describe, expect, it } from "vitest";
import { copy } from "./copy";
import { describeExample } from "./exampleLabels";
import type { ExampleSummary } from "./contracts";

function example(id: string, purpose: string): ExampleSummary {
  return {
    example_id: id, title: id, domain: "hr", purpose,
    task: "do something", character_count: 100,
  };
}

const listing: ExampleSummary[] = [
  example("hr_department_aggregation_001", "department_aggregation"),
  example("hr_department_aggregation_002", "department_aggregation"),
  example("hr_team_summary_001", "team_summary"),
  example("hr_salary_analysis_003", "salary_analysis"),
];

describe("describeExample", () => {
  it("never shows a raw corpus sample id as the label of a known purpose", () => {
    for (const item of listing) {
      const { label } = describeExample(item, listing);
      expect(label).not.toContain(item.example_id);
      expect(label).not.toMatch(/^hr_/);
    }
  });

  it("uses the pt-BR purpose copy as the label", () => {
    const { label } = describeExample(listing[2], listing);
    expect(label).toContain(copy.examplePurposes.team_summary);
  });

  it("numbers examples that share a purpose, so they stay distinguishable", () => {
    const first = describeExample(listing[0], listing).label;
    const second = describeExample(listing[1], listing).label;
    expect(first).not.toBe(second);
    expect(first).toContain("1");
    expect(second).toContain("2");
  });

  it("does not number a purpose that has only one example", () => {
    const { label } = describeExample(listing[3], listing);
    expect(label).toBe(copy.examplePurposes.salary_analysis);
  });

  it("falls back to the raw id for a purpose it does not recognize, never an invented label", () => {
    const unknown = example("hr_future_case_001", "some_new_purpose_added_later");
    const { label, known } = describeExample(unknown, [unknown]);
    expect(known).toBe(false);
    expect(label).toBe("hr_future_case_001");
  });

  it("always exposes the raw id separately as a technical detail", () => {
    const { technicalId } = describeExample(listing[0], listing);
    expect(technicalId).toBe("hr_department_aggregation_001");
  });
});
