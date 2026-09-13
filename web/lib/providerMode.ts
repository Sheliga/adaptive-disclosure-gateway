/**
 * What the UI is allowed to say about which provider answered.
 *
 * Issue #29 requires FakeProvider to be clearly labeled as a deterministic
 * demonstration provider rather than a real model. `GET /health`'s
 * `provider.deterministic_demo_mode` is the fact that supports that claim,
 * so everything hinges on whether that fact is actually in hand.
 *
 * The bug this module fixes is that it used to be modeled as
 * `HealthResponse | null`, where `null` meant two incompatible things:
 * "the request is still in flight" and "the request failed". Both rendered
 * as nothing at all -- so an unreachable or malformed `/health` produced a
 * result screen indistinguishable from a verified real-provider run. The
 * indication whose entire job is to prevent a demonstration from being
 * mistaken for a real model disappeared in exactly the circumstance where
 * nothing could be confirmed.
 *
 * `ProviderModeState` therefore separates the three cases the caller can
 * genuinely be in, and this module maps them to a notice:
 *
 *  - `ready`  -- the question was asked and answered. Announce the demo
 *                provider if that is what health said; say nothing if it
 *                confirmed a real one. Silence here is a positive
 *                statement, backed by an answer.
 *  - `unavailable` -- the question was asked and could not be answered.
 *                Say SO. Not the demo label (that would assert a fact we do
 *                not have, in the direction of "this is only a demo"), not
 *                silence (which reads as the verified real-provider case).
 *                The honest third thing.
 *  - `loading` -- the question is still outstanding. Say nothing: it
 *                resolves on its own in a moment, and surfacing a doubt
 *                that is about to be settled would train the reviewer to
 *                dismiss the notice that actually matters.
 *
 * Note the asymmetry with `unavailable`: a failed check is NOT treated as
 * "assume the worst and print the demo label". Fail-closed here means
 * refusing to assert either provider, because both assertions are wrong
 * when nothing was verified -- claiming a demo when a real provider ran is
 * as false as the reverse, and CLAUDE.md's rule that the UI never invents a
 * fact the API did not give it applies to this fact like any other.
 */

import type { HealthResponse } from "./contracts";
import type { AppCopy } from "./copy";
import { copy as defaultCopy } from "./copy";

export type ProviderModeState =
  | { status: "loading" }
  | { status: "ready"; health: HealthResponse }
  | { status: "unavailable" };

export interface ProviderModeNotice {
  /** Display-ready pt-BR text from `copy.ts` -- never a provider class name. */
  message: string;
  /**
   * Which kind of statement this is, so a component can style it without
   * re-deciding what it means: `demo` is a verified fact about the run,
   * `unverified` is an admission that no fact was obtained.
   */
  tone: "demo" | "external" | "unverified";
}

/**
 * `null` means "there is nothing to say", never "there was nothing to ask".
 *
 * `appCopy` defaults to the pt-BR table so existing callers/tests keep
 * behaving unchanged; a component under `LocaleProvider` passes its
 * resolved `useCopy()` value explicitly (T21 fourth slice / #29).
 */
export function describeProviderMode(
  state: ProviderModeState,
  appCopy: AppCopy = defaultCopy,
): ProviderModeNotice | null {
  switch (state.status) {
    case "loading":
      return null;
    case "unavailable":
      return { message: appCopy.provider.modeUnverifiedLabel, tone: "unverified" };
    case "ready":
      return state.health.provider.deterministic_demo_mode
        ? { message: appCopy.provider.deterministicDemoLabel, tone: "demo" }
        : { message: appCopy.provider.externalModelLabel, tone: "external" };
  }
}
