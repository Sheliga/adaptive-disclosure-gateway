import { describe, expect, it } from "vitest";

import type { HealthResponse } from "./contracts";
import { copy } from "./copy";
import { describeProviderMode, type ProviderModeState } from "./providerMode";

function health(deterministicDemoMode: boolean): HealthResponse {
  return {
    status: "ok",
    contract_version: "t20-application-api-v1",
    provider: {
      provider_class: "FakeProvider",
      model_id: "fake-1",
      model_snapshot: "2026-01-01",
      deterministic_demo_mode: deterministicDemoMode,
    },
    treatments_available: ["b0", "b1", "b2", "b3", "b4"],
  };
}

const ready = (demo: boolean): ProviderModeState => ({ status: "ready", health: health(demo) });

describe("describeProviderMode — a verified answer", () => {
  it("announces the deterministic demo provider when health says so", () => {
    const notice = describeProviderMode(ready(true));

    expect(notice).not.toBeNull();
    expect(notice?.message).toBe(copy.provider.deterministicDemoLabel);
    expect(notice?.tone).toBe("demo");
  });

  it("announces when health confirms an external provider", () => {
    expect(describeProviderMode(ready(false))).toEqual({
      message: copy.provider.externalModelLabel,
      tone: "external",
    });
  });
});

describe("describeProviderMode — an unverifiable answer is not silence", () => {
  it("reports that the mode could not be checked when /health failed", () => {
    // The defect this pins: `health === null` used to mean both "still
    // loading" and "the check failed", so a failed /health silently removed
    // every trace of the provider-mode indication. T21 requires FakeProvider
    // to be distinguishable from a real provider; a missing label is not a
    // distinction, it is the absence of one.
    const notice = describeProviderMode({ status: "unavailable" });

    expect(notice).not.toBeNull();
    expect(notice?.message).toBe(copy.provider.modeUnverifiedLabel);
    expect(notice?.tone).toBe("unverified");
  });

  it("never claims the demo provider when the check failed", () => {
    const notice = describeProviderMode({ status: "unavailable" });

    expect(notice?.message).not.toBe(copy.provider.deterministicDemoLabel);
    expect(notice?.message).not.toContain("FakeProvider");
  });

  it("says nothing while the check is still in flight", () => {
    // "Loading" is genuinely different from "failed": it resolves on its
    // own in a moment, and announcing a doubt that is about to be settled
    // would train the reviewer to ignore the notice that matters.
    expect(describeProviderMode({ status: "loading" })).toBeNull();
  });
});
