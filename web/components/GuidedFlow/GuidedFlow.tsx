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
 */

import { useEffect, useReducer, useState } from "react";

import { executeDisclosure, getExamples, getHealth, previewDisclosure, type DisplayError } from "@/lib/api";
import type { ExampleSummary } from "@/lib/contracts";
import { copy } from "@/lib/copy";
import { buildRequestBody, flowReducer, initialFlowState, type ComposeState } from "@/lib/flow";
import type { ProviderModeState } from "@/lib/providerMode";

import { ComposeScreen } from "../ComposeScreen/ComposeScreen";
import { ProcessingStatus } from "../ProcessingStatus/ProcessingStatus";
import { ResultScreen } from "../ResultScreen/ResultScreen";
import { ReviewScreen } from "../ReviewScreen/ReviewScreen";
import { ThemeToggle } from "../ThemeToggle/ThemeToggle";
import { WelcomeScreen } from "../WelcomeScreen/WelcomeScreen";
import styles from "./GuidedFlow.module.css";

export function GuidedFlow() {
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
    const result = await previewDisclosure(body);
    if (result.ok) {
      dispatch({ type: "PREVIEW_SUCCEEDED", preview: result.data });
    } else {
      dispatch({ type: "PREVIEW_FAILED", error: result.error });
    }
  }

  async function handleConfirmReview(compose: ComposeState) {
    dispatch({ type: "CONFIRM_REVIEW" });
    const body = buildRequestBody(compose);
    const result = await executeDisclosure(body);
    if (result.ok) {
      dispatch({ type: "EXECUTE_SUCCEEDED", execute: result.data });
    } else {
      dispatch({ type: "EXECUTE_FAILED", error: result.error });
    }
  }

  return (
    <div className={styles.app}>
      <header className={styles.header}>
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
            onRestart={() => dispatch({ type: "RESTART" })}
          />
        )}
      </main>
    </div>
  );
}
