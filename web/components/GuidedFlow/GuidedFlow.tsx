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

import { useCallback, useEffect, useRef, useState } from "react";

import {
  compareStrategies,
  executeDocument,
  executeDisclosure,
  getDemoFeatures,
  getDocumentTypes,
  getExamples,
  getHealth,
  previewDisclosure,
  previewDocument,
  type DisplayError,
} from "@/lib/api";
import type { DocumentType, ExampleSummary } from "@/lib/contracts";
import {
  buildDocumentFormData,
  buildRequestBody,
  flowReducer,
  initialFlowState,
  type FlowEvent,
  type ComposeState,
  type FlowState,
} from "@/lib/flow";
import type { ProviderModeState } from "@/lib/providerMode";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { useLocale } from "@/i18n/useLocale";

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

type PrimaryStep = "intro" | "prepare" | "review" | "send" | "result";
type UrlStep = PrimaryStep | "comparison" | "technical";
type GuidedFlowEvent =
  | FlowEvent
  | { type: "BACK_TO_WELCOME" }
  | { type: "RESTORE_NAVIGATION_STATE"; state: FlowState };

const PRIMARY_STEPS: PrimaryStep[] = ["intro", "prepare", "review", "send", "result"];

const STEP_LABELS = {
  "pt-BR": {
    intro: "Introdução",
    prepare: "Preparar",
    review: "Revisar",
    send: "Enviar",
    result: "Resultado",
    comparison: "Comparação",
    technical: "Detalhes técnicos",
    back: "Voltar",
    recoveryHeading: "Esta etapa não pode ser restaurada",
    recoveryBody:
      "Por segurança, o fluxo não salva documentos, tarefas, tokens ou payloads na URL ou no navegador. Inicie novamente para reconstruir esta etapa.",
    recoveryAction: "Voltar à introdução",
    currentStepPrefix: "Etapa atual:",
  },
  en: {
    intro: "Introduction",
    prepare: "Prepare",
    review: "Review",
    send: "Send",
    result: "Result",
    comparison: "Comparison",
    technical: "Technical details",
    back: "Back",
    recoveryHeading: "This step cannot be restored",
    recoveryBody:
      "For safety, the flow does not save documents, tasks, tokens, or payloads in the URL or browser storage. Start again to rebuild this step.",
    recoveryAction: "Back to introduction",
    currentStepPrefix: "Current step:",
  },
} as const;

function primaryStepForState(state: FlowState): PrimaryStep {
  switch (state.screen) {
    case "welcome":
      return "intro";
    case "compose":
    case "previewing":
      return "prepare";
    case "review":
      return "review";
    case "executing":
      return "send";
    case "result":
    case "technicalDetails":
    case "comparing":
    case "comparison":
      return "result";
  }
}

function urlStepForState(state: FlowState): UrlStep {
  if (state.screen === "comparison") {
    return "comparison";
  }
  if (state.screen === "technicalDetails") {
    return "technical";
  }
  return primaryStepForState(state);
}

function urlStepFromSearch(search: string): UrlStep | null {
  const value = new URLSearchParams(search).get("step");
  if (
    value === "intro" ||
    value === "prepare" ||
    value === "review" ||
    value === "send" ||
    value === "result" ||
    value === "comparison" ||
    value === "technical"
  ) {
    return value;
  }
  return null;
}

function replaceStepInUrl(step: UrlStep) {
  const url = new URL(window.location.href);
  url.searchParams.set("step", step);
  return `${url.pathname}${url.search}${url.hash}`;
}

function reduceGuidedFlow(state: FlowState, event: GuidedFlowEvent): FlowState {
  if (event.type === "RESTORE_NAVIGATION_STATE") {
    return event.state;
  }
  if (event.type === "BACK_TO_WELCOME") {
    return state.screen === "compose" ? initialFlowState : state;
  }
  return flowReducer(state, event);
}

export function GuidedFlow() {
  return (
    <LocaleProvider>
      <GuidedFlowShell />
    </LocaleProvider>
  );
}

function GuidedFlowShell() {
  const { copy, locale } = useLocale();
  const labels = STEP_LABELS[locale];
  const [state, setState] = useState<FlowState>(initialFlowState);
  const [unrecoverableStep, setUnrecoverableStep] = useState<UrlStep | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const historySnapshotsRef = useRef(new Map<string, FlowState>());
  const suppressHistorySyncRef = useRef(false);
  const navigationIdRef = useRef(0);
  const [examples, setExamples] = useState<ExampleSummary[] | null>(null);
  const [examplesError, setExamplesError] = useState<DisplayError | null>(null);
  const [documentTypes, setDocumentTypes] = useState<DocumentType[] | null>(null);
  const [documentTypesError, setDocumentTypesError] = useState<DisplayError | null>(null);
  const [health, setHealth] = useState<ProviderModeState>({ status: "loading" });
  // T28 / issue #70. A UX convenience only, never a security decision --
  // see ReviewScreen's docstring and lib/demoTransparency.ts's own gate,
  // which is what actually decides whether export/restore requests are
  // ever forwarded upstream. Any failure or invalid body from
  // getDemoFeatures is treated as disabled, same posture as `health`.
  const [demoTransparencyEnabled, setDemoTransparencyEnabled] = useState(false);
  // T29 / issue #72. Same posture, read from the SAME single features
  // fetch below rather than a second request -- see
  // `lib/demoVaultExplorer.ts`'s own gate, which is what actually decides
  // whether the vault explorer route ever forwards a request upstream.
  const [demoVaultExplorerEnabled, setDemoVaultExplorerEnabled] = useState(false);

  const dispatch = useCallback((event: GuidedFlowEvent) => {
    if (event.type !== "SET_DOCUMENT_TYPE") {
      setUnrecoverableStep(null);
    }
    setState((current) => reduceGuidedFlow(current, event));
  }, []);

  useEffect(() => {
    const heading = mainRef.current?.querySelector("h1");
    if (!(heading instanceof HTMLElement)) {
      return;
    }
    if (!heading.hasAttribute("tabindex")) {
      heading.setAttribute("tabindex", "-1");
    }
    heading.focus({ preventScroll: true });
  }, [state.screen, unrecoverableStep]);

  useEffect(() => {
    const currentStep = urlStepFromSearch(window.location.search);
    if (currentStep !== null && currentStep !== "intro") {
      setUnrecoverableStep(currentStep);
      suppressHistorySyncRef.current = true;
      window.history.replaceState({ flowNavigationId: null }, "", replaceStepInUrl(currentStep));
    } else {
      const initialId = `flow-${navigationIdRef.current}`;
      historySnapshotsRef.current.set(initialId, initialFlowState);
      window.history.replaceState({ flowNavigationId: initialId }, "", replaceStepInUrl("intro"));
    }

    function handlePopState(event: PopStateEvent) {
      const id =
        typeof event.state?.flowNavigationId === "string" ? event.state.flowNavigationId : null;
      if (id === null) {
        setUnrecoverableStep(urlStepFromSearch(window.location.search) ?? "intro");
        return;
      }
      const snapshot = historySnapshotsRef.current.get(id);
      if (snapshot === undefined) {
        setUnrecoverableStep(urlStepFromSearch(window.location.search) ?? "intro");
        return;
      }
      setUnrecoverableStep(null);
      suppressHistorySyncRef.current = true;
      dispatch({ type: "RESTORE_NAVIGATION_STATE", state: snapshot });
    }

    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
      window.history.replaceState(null, "", replaceStepInUrl("intro"));
    };
  }, [dispatch]);

  useEffect(() => {
    if (unrecoverableStep !== null) {
      return;
    }
    if (suppressHistorySyncRef.current) {
      suppressHistorySyncRef.current = false;
      return;
    }
    const step = urlStepForState(state);
    const currentStep = urlStepFromSearch(window.location.search);
    const id = `flow-${++navigationIdRef.current}`;
    historySnapshotsRef.current.set(id, state);
    const nextUrl = replaceStepInUrl(step);
    if (currentStep === step) {
      window.history.replaceState({ flowNavigationId: id }, "", nextUrl);
      return;
    }
    if (state.screen === "previewing" || state.screen === "executing" || state.screen === "comparing") {
      window.history.replaceState({ flowNavigationId: id }, "", nextUrl);
      return;
    }
    window.history.pushState({ flowNavigationId: id }, "", nextUrl);
  }, [state, unrecoverableStep]);

  useEffect(() => {
    let cancelled = false;
    getDemoFeatures().then((result) => {
      if (cancelled) {
        return;
      }
      setDemoTransparencyEnabled(result.ok && result.data.demo_transparency_enabled);
      setDemoVaultExplorerEnabled(result.ok && result.data.demo_vault_explorer_enabled);
    });
    return () => {
      cancelled = true;
    };
  }, []);

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
    if (
      state.screen !== "compose" ||
      state.compose.documentType !== null ||
      documentTypes === null
    ) {
      return;
    }
    const primary =
      documentTypes.find((item) => item.document_type === "contract") ?? documentTypes[0];
    if (primary) {
      dispatch({
        type: "SET_DOCUMENT_TYPE",
        documentType: primary.document_type,
        analysisMode: primary.default_analysis_mode,
      });
    }
  }, [state, documentTypes, dispatch]);

  useEffect(() => {
    let cancelled = false;
    getDocumentTypes().then((result) => {
      if (cancelled) return;
      if (!result.ok) {
        setDocumentTypesError(result.error);
        return;
      }
      setDocumentTypes(result.data.document_types);
      const primary =
        result.data.document_types.find((item) => item.document_type === "contract") ??
        result.data.document_types[0];
      if (primary) {
        dispatch({
          type: "SET_DOCUMENT_TYPE",
          documentType: primary.document_type,
          analysisMode: primary.default_analysis_mode,
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [dispatch]);

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
    if (compose.mode === "upload") {
      const result = await previewDocument(buildDocumentFormData(compose), copy);
      if (result.ok) {
        const { confirmation_token, ...preview } = result.data;
        dispatch({ type: "PREVIEW_SUCCEEDED", preview, confirmationToken: confirmation_token });
      } else {
        dispatch({ type: "PREVIEW_FAILED", error: result.error });
      }
      return;
    }
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

  async function handleConfirmReview(review: Extract<FlowState, { screen: "review" }>) {
    dispatch({ type: "CONFIRM_REVIEW" });
    if (review.compose.mode === "upload") {
      if (review.confirmationToken === null) {
        dispatch({
          type: "EXECUTE_FAILED",
          error: { message: copy.errors.previewExpired, kind: "PreviewConfirmationError", fields: null },
          requiresNewPreview: true,
        });
        return;
      }
      const result = await executeDocument(
        buildDocumentFormData(review.compose, review.confirmationToken),
        copy,
      );
      if (result.ok) {
        dispatch({ type: "EXECUTE_SUCCEEDED", execute: result.data });
      } else {
        dispatch({
          type: "EXECUTE_FAILED",
          error: result.error,
          requiresNewPreview: result.error.kind === "PreviewConfirmationError",
        });
      }
      return;
    }
    const compose = review.compose;
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
    if (compose.mode === "upload") {
      dispatch({
        type: "COMPARE_FAILED",
        error: {
          message: copy.errors.comparisonUnavailableForUpload,
          kind: "UnsupportedDocumentComparison",
          fields: null,
        },
      });
      return;
    }
    const body = buildRequestBody(compose);
    const result = await compareStrategies(body, copy);
    if (result.ok) {
      dispatch({ type: "COMPARE_SUCCEEDED", comparison: result.data });
    } else {
      dispatch({ type: "COMPARE_FAILED", error: result.error });
    }
  }

  function resetAfterUnrecoverableStep() {
    setUnrecoverableStep(null);
    dispatch({ type: "RESTORE_NAVIGATION_STATE", state: initialFlowState });
  }

  function handleBack() {
    switch (state.screen) {
      case "compose":
        dispatch({ type: "BACK_TO_WELCOME" });
        break;
      case "review":
        dispatch({ type: "CANCEL_REVIEW" });
        break;
      case "technicalDetails":
      case "comparison":
        dispatch({ type: "RETURN_TO_RESULT" });
        break;
      default:
        break;
    }
  }

  const showBackButton =
    state.screen === "compose" ||
    state.screen === "review" ||
    state.screen === "technicalDetails" ||
    state.screen === "comparison";

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <LocaleSwitcher />
        <ThemeToggle />
      </header>
      <main ref={mainRef} className={styles.main}>
        <nav className={styles.progress} aria-label={labels.currentStepPrefix}>
          <ol className={styles.progressList}>
            {PRIMARY_STEPS.map((step) => {
              const current = step === primaryStepForState(state);
              return (
                <li
                  key={step}
                  className={`${styles.progressItem} ${current ? styles.progressItemCurrent : ""}`}
                  aria-current={current ? "step" : undefined}
                >
                  <span className={styles.progressMarker} aria-hidden="true" />
                  <span className={styles.progressLabel}>{labels[step]}</span>
                </li>
              );
            })}
          </ol>
        </nav>

        {showBackButton && (
          <div className={styles.backBar}>
            <button type="button" className={styles.backButton} onClick={handleBack}>
              {labels.back}
            </button>
          </div>
        )}

        {unrecoverableStep !== null && (
          <section aria-labelledby="navigation-recovery-heading" className={styles.recovery}>
            <p className={styles.recoveryStep}>
              {labels.currentStepPrefix} {labels[unrecoverableStep]}
            </p>
            <h1 id="navigation-recovery-heading">{labels.recoveryHeading}</h1>
            <p>{labels.recoveryBody}</p>
            <button type="button" className={styles.backButton} onClick={resetAfterUnrecoverableStep}>
              {labels.recoveryAction}
            </button>
          </section>
        )}

        {unrecoverableStep === null && state.screen === "welcome" && (
          <WelcomeScreen onStart={() => dispatch({ type: "START_TEST" })} />
        )}

        {unrecoverableStep === null && state.screen === "compose" && (
          <ComposeScreen
            compose={state.compose}
            submitError={state.submitError}
            examples={examples}
            examplesError={examplesError}
            documentTypes={documentTypes}
            documentTypesError={documentTypesError}
            dispatch={dispatch}
            onSubmit={() => handleSubmitCompose(state.compose)}
          />
        )}

        {unrecoverableStep === null && state.screen === "previewing" && (
          <ProcessingStatus
            stages={
              state.compose.mode === "upload"
                ? [
                    copy.processingStages.readingFile,
                    copy.processingStages.analyzingDocument,
                    copy.processingStages.detectingSensitiveData,
                    copy.processingStages.applyingDisclosurePolicy,
                  ]
                : [
                    copy.processingStages.detectingSensitiveData,
                    copy.processingStages.applyingDisclosurePolicy,
                  ]
            }
          />
        )}

        {unrecoverableStep === null && state.screen === "review" && (
          <ReviewScreen
            preview={state.preview}
            executeError={state.executeError}
            onConfirm={() => handleConfirmReview(state)}
            onCancel={() => dispatch({ type: "CANCEL_REVIEW" })}
            compose={state.compose}
            demoTransparencyEnabled={demoTransparencyEnabled}
            demoVaultExplorerEnabled={demoVaultExplorerEnabled}
          />
        )}

        {unrecoverableStep === null && state.screen === "executing" && (
          <ProcessingStatus
            stages={[copy.processingStages.consultingModel, copy.processingStages.reconstructingAnswer]}
          />
        )}

        {unrecoverableStep === null && state.screen === "result" && (
          <ResultScreen
            execute={state.execute}
            health={health}
            compareError={state.compareError}
            onRestart={() => dispatch({ type: "RESTART" })}
            onCompareStrategies={() => handleRequestComparison(state.compose)}
            onViewTechnicalDetails={() => dispatch({ type: "OPEN_TECHNICAL_DETAILS" })}
            demoVaultExplorerEnabled={demoVaultExplorerEnabled}
            vaultExplorerToken={state.preview.vault_explorer_token}
          />
        )}

        {unrecoverableStep === null && state.screen === "technicalDetails" && (
          <TechnicalDetailsScreen
            execute={state.execute}
            onBack={() => dispatch({ type: "RETURN_TO_RESULT" })}
          />
        )}

        {unrecoverableStep === null && state.screen === "comparing" && (
          <ProcessingStatus stages={[copy.processingStages.comparingStrategies]} />
        )}

        {unrecoverableStep === null && state.screen === "comparison" && (
          <ComparisonScreen
            comparison={state.comparison}
            onBack={() => dispatch({ type: "RETURN_TO_RESULT" })}
          />
        )}
      </main>
    </div>
  );
}
