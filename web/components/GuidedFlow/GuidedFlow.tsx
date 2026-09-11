"use client";

/**
 * The guided flow's orchestrator: owns the `useReducer(flowReducer, ...)`
 * instance (`lib/flow.ts`) and is the ONLY place that calls the typed API
 * client (`lib/api.ts`). Every screen component below it is a pure
 * presentational function of props -- this is what makes "execute is never
 * called until the user confirms on the review step" a property of the
 * wiring here rather than something each screen has to individually get
 * right.
 *
 * `getExamples`/`getHealth` are fetched once, lazily: examples on first
 * reaching the compose screen, health up front (its only consumer,
 * `ResultScreen`'s provider-mode notice, needs it by the time the result
 * screen renders, and a shared, once-only fetch is simpler than threading a
 * loading state through the whole flow for it).
 *
 * Health is held as a three-state `ProviderModeState`, not as
 * `HealthResponse | null`. A failed `getHealth` must stay distinguishable
 * from one still in flight all the way down to the screen that renders it:
 * collapsing both into `null` is what previously made an unreachable
 * `/health` silently erase the FakeProvider indication instead of
 * reporting that it could not be verified. See `lib/providerMode.ts`.
 *
 * Wrapped in `LocaleProvider` (T21 fourth slice / #29) here rather than in
 * `app/layout.tsx`: `app/page.tsx`'s own docstring already calls this
 * component "the whole app for this slice", and `ThemeToggle`/
 * `LocaleSwitcher` both live in its header, so the locale/theme shell
 * concerns stay together. Every screen below reads the resolved copy table
 * via `useCopy()` (or, for the two-argument `lib/*.ts` helpers, receives it
 * explicitly) -- never a static `import { copy } from "@/lib/copy"` -- so a
 * locale switch anywhere under this provider re-renders with the new
 * language without a reload and without re-fetching `/preview`, `/execute`
 * or `/compare`.
 */

import { useEffect, useReducer, useState } from "react";

import {
  compareStrategies,
  executeDisclosure,
  getExamples,
  getHealth,
  previewDisclosure,
  type DisplayError,
} from "@/lib/api";
import type { ExampleSummary } from "@/lib/contracts";
import { buildRequestBody, flowReducer, initialFlowState, type ComposeState } from "@/lib/flow";
import type { ProviderModeState } from "@/lib/providerMode";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { useCopy } from "@/i18n/useLocale";

import { ComparisonScreen } from "../ComparisonScreen/ComparisonScreen";
import { ComposeScreen } from "../ComposeScreen/ComposeScreen";
import { LocaleSwitcher } from "../LocaleSwitcher/LocaleSwitcher";
import { ProcessingStatus } from "../ProcessingStatus/ProcessingStatus";
import { ResultScreen } from "../ResultScreen/ResultScreen";
import { ReviewScreen } from "../ReviewScreen/ReviewScreen";
import { TechnicalDetailsScreen } from "../TechnicalDetailsScreen/TechnicalDetailsScreen";
import { ThemeToggle } from "../ThemeToggle/ThemeToggle";
import { WelcomeScreen } from "../WelcomeScreen/WelcomeScreen";
import styles from "./GuidedFlow.module.css";

export function GuidedFlow() {
  return (
    <LocaleProvider>
      <GuidedFlowShell />
    </LocaleProvider>
  );
}

function GuidedFlowShell() {
  const copy = useCopy();
  const [state, dispatch] = useReducer(flowReducer, initialFlowState);
  const [examples, setExamples] = useState<ExampleSummary[] | null>(null);
  const [examplesError, setExamplesError] = useState<DisplayError | null>(null);
  const [health, setHealth] = useState<ProviderModeState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getHealth().then((result) => {
      if (cancelled) {
        return;
      }
      // A failure is recorded as `unavailable`, never left as the initial
      // "loading" -- the whole point of the three-state value is that the
      // screen can tell "we could not check" from "we have not checked yet".
      setHealth(result.ok ? { status: "ready", health: result.data } : { status: "unavailable" });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (state.screen !== "compose" || examples !== null || examplesError !== null) {
      return;
    }
    let cancelled = false;
    getExamples().then((result) => {
      if (cancelled) {
        return;
      }
      if (result.ok) {
        setExamples(result.data.examples);
      } else {
        setExamplesError(result.error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [state.screen, examples, examplesError]);

  async function handleSubmitCompose(compose: ComposeState) {
    dispatch({ type: "SUBMIT_COMPOSE" });
    const body = buildRequestBody(compose);
    // `copy` is the CURRENT locale's table, read from this render's closure
    // -- never a dependency of an effect, so switching locale never
    // retriggers this call; it only changes what a FUTURE click submits
    // errors in, exactly like the request body already behaves.
    const result = await previewDisclosure(body, copy);
    if (result.ok) {
      dispatch({ type: "PREVIEW_SUCCEEDED", preview: result.data });
    } else {
      dispatch({ type: "PREVIEW_FAILED", error: result.error });
    }
  }

  async function handleConfirmReview(compose: ComposeState) {
    dispatch({ type: "CONFIRM_REVIEW" });
    const body = buildRequestBody(compose);
    const result = await executeDisclosure(body, copy);
    if (result.ok) {
      dispatch({ type: "EXECUTE_SUCCEEDED", execute: result.data });
    } else {
      dispatch({ type: "EXECUTE_FAILED", error: result.error });
    }
  }

  /**
   * Reuses `buildRequestBody(compose)` unchanged -- the SAME content/task
   * the original preview/execute calls used for this run, never re-entered
   * or re-derived. `POST /disclosure/compare` ignores `body.strategy`
   * regardless, so this is exactly the same body `handleSubmitCompose`/
   * `handleConfirmReview` already send.
   */
  async function handleRequestComparison(compose: ComposeState) {
    dispatch({ type: "REQUEST_COMPARISON" });
    const body = buildRequestBody(compose);
    const result = await compareStrategies(body, copy);
    if (result.ok) {
      dispatch({ type: "COMPARE_SUCCEEDED", comparison: result.data });
    } else {
      dispatch({ type: "COMPARE_FAILED", error: result.error });
    }
  }

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <LocaleSwitcher />
        <ThemeToggle />
      </header>
      <main className={styles.main}>
        {state.screen === "welcome" && (
          <WelcomeScreen onStart={() => dispatch({ type: "START_TEST" })} />
        )}

        {state.screen === "compose" && (
          <ComposeScreen
            compose={state.compose}
            submitError={state.submitError}
            examples={examples}
            examplesError={examplesError}
            dispatch={dispatch}
            onSubmit={() => handleSubmitCompose(state.compose)}
          />
        )}

        {state.screen === "previewing" && (
          <ProcessingStatus
            stages={[
              copy.processingStages.detectingSensitiveData,
              copy.processingStages.applyingDisclosurePolicy,
            ]}
          />
        )}

        {state.screen === "review" && (
          <ReviewScreen
            preview={state.preview}
            executeError={state.executeError}
            onConfirm={() => handleConfirmReview(state.compose)}
            onCancel={() => dispatch({ type: "CANCEL_REVIEW" })}
          />
        )}

        {state.screen === "executing" && (
          <ProcessingStatus
            stages={[copy.processingStages.consultingModel, copy.processingStages.reconstructingAnswer]}
          />
        )}

        {state.screen === "result" && (
          <ResultScreen
            execute={state.execute}
            health={health}
            compareError={state.compareError}
            onRestart={() => dispatch({ type: "RESTART" })}
            onCompareStrategies={() => handleRequestComparison(state.compose)}
            onViewTechnicalDetails={() => dispatch({ type: "OPEN_TECHNICAL_DETAILS" })}
          />
        )}

        {state.screen === "technicalDetails" && (
          <TechnicalDetailsScreen
            execute={state.execute}
            onBack={() => dispatch({ type: "RETURN_TO_RESULT" })}
          />
        )}

        {state.screen === "comparing" && (
          <ProcessingStatus stages={[copy.processingStages.comparingStrategies]} />
        )}

        {state.screen === "comparison" && (
          <ComparisonScreen
            comparison={state.comparison}
            onBack={() => dispatch({ type: "RETURN_TO_RESULT" })}
          />
        )}
      </main>
    </div>
  );
}
