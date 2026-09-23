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
import type { DocumentType, ExampleSummary, ExecuteResponse } from "@/lib/contracts";
import {
  approveReview,
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

import { ApprovedReviewScreen } from "../ApprovedReviewScreen/ApprovedReviewScreen";
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
    case "approvedReview":
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

/**
 * Marks history entries as never restorable again and drops their snapshots
 * immediately (nothing sensitive is retained for an entry that can only
 * ever fail closed). The ids stay in the tracked entry list on purpose: the
 * browser still physically has those entries, so a popstate onto one must
 * still update the tracked position (see handlePopState) before it fails
 * closed, and a later push still prunes them as a discarded branch.
 */
function invalidateHistoryEntries(
  ids: readonly string[],
  snapshots: Map<string, FlowState>,
  nonRestorable: Set<string>,
) {
  for (const id of ids) {
    snapshots.delete(id);
    nonRestorable.add(id);
  }
}

/**
 * Whether a same-entry history write is a Compose input edit. Every compose
 * setter (SET_MODE, SELECT_EXAMPLE, SET_PASTED_TEXT, SET_FILE,
 * SET_FILE_ERROR, CLEAR_FILE, SET_TASK, SET_DOCUMENT_TYPE,
 * SET_ANALYSIS_MODE) goes through `composeReducer`, which returns a NEW
 * `compose` object, and nothing else on the Compose screen does (a preview
 * failure carries the same object through "previewing"). So comparing the
 * `compose` identity against the entry's recorded snapshot catches every
 * edit -- including setters added later -- without listing them here.
 */
function isComposeEdit(previous: FlowState | undefined, next: FlowState) {
  return (
    previous !== undefined &&
    previous.screen === "compose" &&
    next.screen === "compose" &&
    previous.compose !== next.compose
  );
}

function isStableNavigationState(state: FlowState) {
  return (
    state.screen === "welcome" ||
    state.screen === "compose" ||
    state.screen === "review" ||
    state.screen === "approvedReview" ||
    state.screen === "result" ||
    state.screen === "technicalDetails" ||
    state.screen === "comparison"
  );
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
  const stateRef = useRef(state);
  stateRef.current = state;
  const mainRef = useRef<HTMLElement>(null);
  // Invariant: this Map holds exactly the snapshots of entries at or before
  // historyIndexRef.current, plus any still-reachable forward entries. A
  // push is a new branch: every entry after the current index is deleted
  // (snapshot + non-restorable mark) before the new one is recorded -- see
  // the push effect below. A non-restorable entry's own snapshot is deleted
  // the moment it is marked (see invalidateHistoryEntry), rather than
  // waiting for a future push, since it can never be restored anyway.
  //
  // T32.2 / #102 adds two in-place rewrites of that Map, both in memory only:
  //  - a successful send REPLACES the sending Review's snapshot with its
  //    token-free "approvedReview" form (recordApprovedReview), instead of
  //    deleting it; Result -> Back then shows the read-only Approved Review;
  //  - the first compose edit on an entry that has forward entries
  //    invalidates every one of them (invalidateForwardEntries, called from
  //    the history-sync effect): an old Review -- and its confirmation
  //    token -- can never be reached again by Forward once the request it
  //    reviewed has changed. Any input edit after Review therefore requires
  //    a new preview before a send action exists again.
  const historySnapshotsRef = useRef(new Map<string, FlowState>());
  const historyEntryIdsRef = useRef<string[]>([]);
  const historyIndexRef = useRef(0);
  const currentNavigationIdRef = useRef<string | null>(null);
  const nonRestorableNavigationIdsRef = useRef(new Set<string>());
  // A corrective `history.go(...)` in flight (see handlePopState's executing
  // lock): non-null from the moment it is requested until the popstate
  // landing on `expectedId` (the sending Review's entry) arrives. While it is
  // non-null the browser is NOT at currentNavigationIdRef, so:
  //  - the history-sync effect must not push/replace (it would write
  //    relative to the wrong entry -- e.g. a Result pushed while the browser
  //    is physically on Compose discards the Review and forks history);
  //  - any other popstate is corrected again toward `expectedId`, even if
  //    execute has meanwhile settled, never restored on its own merits;
  //  - only the popstate for `expectedId` is swallowed. Completing the
  //    correction bumps `historySyncEpoch` so the sync effect re-runs once
  //    and registers whatever state execute left behind (Result, or Review
  //    with an error) against the now-correct browser position.
  const historyCorrectionRef = useRef<{ expectedId: string } | null>(null);
  const [historySyncEpoch, setHistorySyncEpoch] = useState(0);
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
      currentNavigationIdRef.current = initialId;
      historyEntryIdsRef.current = [initialId];
      historyIndexRef.current = 0;
      historySnapshotsRef.current.set(initialId, initialFlowState);
      window.history.replaceState({ flowNavigationId: initialId }, "", replaceStepInUrl("intro"));
    }

    function handlePopState(event: PopStateEvent) {
      const id =
        typeof event.state?.flowNavigationId === "string" ? event.state.flowNavigationId : null;
      const targetIndex = id === null ? -1 : historyEntryIdsRef.current.indexOf(id);
      const correction = historyCorrectionRef.current;
      if (correction !== null && id === correction.expectedId) {
        // This is the corrective popstate our own history.go(...) call
        // (below) triggered to undo an out-of-band Back/Forward while a
        // send was in flight -- the browser is back on the sending entry,
        // which historyIndexRef/currentNavigationIdRef never stopped
        // pointing at. Any state execute settled into meanwhile was held
        // back by the sync effect; the epoch bump lets it sync now, once.
        historyCorrectionRef.current = null;
        setHistorySyncEpoch((epoch) => epoch + 1);
        return;
      }
      if (correction !== null || stateRef.current.screen === "executing") {
        // A send is in flight, or has just settled but the browser has not
        // yet returned to the entry it was sent from. The only history
        // entry that legitimately exists for it is the Review entry that
        // triggered it -- still historyIndexRef.current, since entering
        // "executing" never pushes a new entry and the sync effect holds
        // back while a correction is pending. Any Back/Forward landing
        // anywhere else -- a known earlier entry, or a target we don't even
        // recognize -- must not be presented as the send having been
        // cancelled: falling through to Compose/Review would offer a resend
        // the user never asked for, and the generic unrecoverable screen
        // would hide an in-flight request behind "start again". So the
        // browser position is corrected back to the sending entry instead,
        // from wherever THIS popstate says the browser now is (a second
        // Back racing ahead of an earlier correction is re-corrected, not
        // silently eaten or restored). The delta is exact when the target
        // is a known entry; for an unrecognized one we cannot compute the
        // real distance, so a single corrective step is the simplest safe
        // fallback (the common case of one Back past the sending entry).
        const expectedId = correction?.expectedId ?? currentNavigationIdRef.current;
        if (expectedId === null) {
          return;
        }
        const expectedIndex = historyEntryIdsRef.current.indexOf(expectedId);
        if (targetIndex >= 0 && targetIndex === expectedIndex) {
          // Already on the sending entry with no correction outstanding:
          // nothing to undo, and restoring its Review snapshot here would
          // put a Confirm button in front of an in-flight send.
          return;
        }
        const delta = targetIndex >= 0 ? expectedIndex - targetIndex : 1;
        historyCorrectionRef.current = { expectedId };
        window.history.go(delta);
        return;
      }
      if (id === null || targetIndex < 0) {
        setUnrecoverableStep(urlStepFromSearch(window.location.search) ?? "intro");
        return;
      }
      const snapshot = historySnapshotsRef.current.get(id);
      if (
        snapshot === undefined ||
        !isStableNavigationState(snapshot) ||
        nonRestorableNavigationIdsRef.current.has(id)
      ) {
        // The browser has genuinely moved to this entry even though it
        // cannot be restored, so the tracked position must follow (see the
        // Map's invariant comment above) -- otherwise a later push prunes
        // nothing and a stale snapshot beyond this point (e.g. a completed
        // Result carrying execute data) is retained indefinitely.
        historyIndexRef.current = targetIndex;
        currentNavigationIdRef.current = id;
        setUnrecoverableStep(urlStepFromSearch(window.location.search) ?? "intro");
        return;
      }
      historyIndexRef.current = targetIndex;
      currentNavigationIdRef.current = id;
      setUnrecoverableStep(null);
      if (snapshot === stateRef.current) {
        // The browser has landed back on the entry the flow is ALREADY
        // showing (e.g. a same-id popstate, or one that raced an earlier
        // correction): the tracked position above still needed updating,
        // but dispatching RESTORE_NAVIGATION_STATE here would hand the
        // reducer the very same FlowState object it already holds. React
        // bails out of a setState that returns the previous state -- no
        // re-render, so the history-sync effect (the only place that reads
        // and clears suppressHistorySyncRef) would never run. Arming the
        // flag here would then leave it stuck `true` for the NEXT, real
        // transition, which would silently skip its own history write.
        // Suppress may only be armed when a state change is guaranteed to
        // follow and run that effect, so this case skips both.
        return;
      }
      suppressHistorySyncRef.current = true;
      dispatch({ type: "RESTORE_NAVIGATION_STATE", state: snapshot });
    }

    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
      // A correction still in flight belongs to this listener's lifetime:
      // its popstate can no longer reach us, so it must not survive into a
      // remount (StrictMode/Fast Refresh keep refs) and hold the sync back.
      historyCorrectionRef.current = null;
      window.history.replaceState(null, "", replaceStepInUrl("intro"));
    };
  }, [dispatch]);

  useEffect(() => {
    if (unrecoverableStep !== null || !isStableNavigationState(state)) {
      return;
    }
    if (historyCorrectionRef.current !== null) {
      // The browser is not at currentNavigationIdRef yet (see
      // historyCorrectionRef): writing now would target the wrong entry.
      // Completing the correction bumps historySyncEpoch, re-running this
      // effect with whatever state is current by then.
      return;
    }
    if (suppressHistorySyncRef.current) {
      suppressHistorySyncRef.current = false;
      return;
    }
    const step = urlStepForState(state);
    const currentStep = urlStepFromSearch(window.location.search);
    const currentId = currentNavigationIdRef.current;
    const nextUrl = replaceStepInUrl(step);
    if (currentId !== null && currentStep === step) {
      const recorded = historySnapshotsRef.current.get(currentId);
      if (recorded === state) {
        // This exact state is already registered on this very entry, so
        // there is nothing to write. This happens when the effect re-runs
        // for another dependency after already syncing: e.g. React defers
        // the passive effect of the commit that rendered Result past the
        // corrective popstate (#101/#105), so that deferred run pushes
        // Result, and the historySyncEpoch bump from the same popstate
        // re-runs the effect over the SAME state. Without this check, that
        // second run wrote a redundant replaceState of the entry it had
        // just pushed (a pre-existing, load-dependent flake in the race
        // tests, which pin the exact history writes).
        return;
      }
      if (isComposeEdit(recorded, state)) {
        // Stale-Review policy (#102): the request changed after it may have
        // been reviewed, so every forward entry (an old Review with its
        // token, or an Approved Review/Result further on) is invalidated on
        // this first edit. Forward then fails closed; the only way on is a
        // new preview, whose push prunes these entries for good.
        invalidateHistoryEntries(
          historyEntryIdsRef.current.slice(historyIndexRef.current + 1),
          historySnapshotsRef.current,
          nonRestorableNavigationIdsRef.current,
        );
      }
      historySnapshotsRef.current.set(currentId, state);
      window.history.replaceState({ flowNavigationId: currentId }, "", nextUrl);
      return;
    }
    // This is the push side of the Map's invariant (see historySnapshotsRef's
    // declaration): the Map holds exactly the snapshots of entries at or
    // before the current index plus reachable forward entries; on push,
    // every entry after the current index is deleted (snapshot +
    // non-restorable mark) -- this is a new branch, so nothing after
    // historyIndexRef.current is reachable anymore.
    const abandonedIds = historyEntryIdsRef.current.slice(historyIndexRef.current + 1);
    for (const abandonedId of abandonedIds) {
      historySnapshotsRef.current.delete(abandonedId);
      nonRestorableNavigationIdsRef.current.delete(abandonedId);
    }
    historyEntryIdsRef.current = historyEntryIdsRef.current.slice(0, historyIndexRef.current + 1);
    const id = `flow-${++navigationIdRef.current}`;
    currentNavigationIdRef.current = id;
    historySnapshotsRef.current.set(id, state);
    historyEntryIdsRef.current.push(id);
    historyIndexRef.current = historyEntryIdsRef.current.length - 1;
    window.history.pushState({ flowNavigationId: id }, "", nextUrl);
  }, [state, unrecoverableStep, historySyncEpoch]);

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

  /**
   * Converts the sending Review's history snapshot, in place, into its
   * token-free Approved Review form (#102) -- the same policy for the upload
   * and paste/example paths, called only once execute has SUCCEEDED. Only
   * an entry that is still tracked and restorable is converted: if it was
   * pruned or invalidated meanwhile, it stays gone rather than being
   * resurrected. The approved snapshot lives in the same in-memory Map as
   * every other snapshot, so the same pruning removes it with its branch.
   */
  function recordApprovedReview(
    reviewNavigationId: string | null,
    review: Extract<FlowState, { screen: "review" }>,
  ) {
    if (
      reviewNavigationId === null ||
      !historySnapshotsRef.current.has(reviewNavigationId) ||
      nonRestorableNavigationIdsRef.current.has(reviewNavigationId)
    ) {
      return;
    }
    historySnapshotsRef.current.set(reviewNavigationId, approveReview(review));
  }

  /**
   * Execute's outcome, shared by both request paths so they cannot diverge:
   *  - success: the Review becomes the Approved Review, then Result;
   *  - a confirmation the backend rejects as expired/invalid: the Review
   *    entry (and the token its snapshot holds) is invalidated, so browser
   *    Back cannot offer it again -- Compose, with its fields, is the only
   *    way on, through a new preview;
   *  - any other failure: stays a live Review with the error; nothing is
   *    retried automatically, and a new attempt is an explicit Confirm.
   */
  function settleExecute(
    reviewNavigationId: string | null,
    review: Extract<FlowState, { screen: "review" }>,
    outcome:
      | { ok: true; execute: ExecuteResponse }
      | { ok: false; error: DisplayError; requiresNewPreview: boolean },
  ) {
    if (outcome.ok) {
      recordApprovedReview(reviewNavigationId, review);
      dispatch({ type: "EXECUTE_SUCCEEDED", execute: outcome.execute });
      return;
    }
    if (outcome.requiresNewPreview && reviewNavigationId !== null) {
      invalidateHistoryEntries(
        [reviewNavigationId],
        historySnapshotsRef.current,
        nonRestorableNavigationIdsRef.current,
      );
    }
    dispatch({
      type: "EXECUTE_FAILED",
      error: outcome.error,
      requiresNewPreview: outcome.requiresNewPreview,
    });
  }

  async function handleConfirmReview(review: Extract<FlowState, { screen: "review" }>) {
    const reviewNavigationId = currentNavigationIdRef.current;
    dispatch({ type: "CONFIRM_REVIEW" });
    if (review.compose.mode === "upload") {
      if (review.confirmationToken === null) {
        settleExecute(reviewNavigationId, review, {
          ok: false,
          error: { message: copy.errors.previewExpired, kind: "PreviewConfirmationError", fields: null },
          requiresNewPreview: true,
        });
        return;
      }
      const result = await executeDocument(
        buildDocumentFormData(review.compose, review.confirmationToken),
        copy,
      );
      settleExecute(
        reviewNavigationId,
        review,
        result.ok
          ? { ok: true, execute: result.data }
          : {
              ok: false,
              error: result.error,
              requiresNewPreview: result.error.kind === "PreviewConfirmationError",
            },
      );
      return;
    }
    const result = await executeDisclosure(buildRequestBody(review.compose), copy);
    settleExecute(
      reviewNavigationId,
      review,
      result.ok
        ? { ok: true, execute: result.data }
        : { ok: false, error: result.error, requiresNewPreview: false },
    );
  }

  /**
   * Reuses `buildRequestBody(compose)` unchanged -- the SAME content/task
   * the original preview/execute calls used for this run, never re-entered
   * or re-derived. `POST /disclosure/compare` ignores `body.strategy`
   * regardless, so this is exactly the same body `handleSubmitCompose`/
   * `handleConfirmReview` already send.
   */
  async function handleRequestComparison(compose: ComposeState) {
    if (historyCorrectionRef.current !== null) {
      // Same guard as handleRestart/handleViewTechnicalDetails below: a
      // corrective history.go(...) is still in flight (see
      // historyCorrectionRef's declaration), so the browser is not at
      // currentNavigationIdRef yet. Requesting a comparison now would both
      // fire `/disclosure/compare` and let the history-sync effect's later
      // push write "comparing"/"comparison" relative to the wrong entry,
      // discarding Result before it is ever registered in history (#101).
      return;
    }
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
    window.history.back();
  }

  function handleForward() {
    window.history.forward();
  }

  /**
   * Result-action lock during a pending correction (#101 follow-up): execute
   * can settle to "result" BEFORE the corrective popstate that
   * historyCorrectionRef is waiting for (see its declaration and the
   * history-sync effect above, which already holds the write back for
   * exactly this reason). Result renders and stays visible -- that is
   * correct and must not change -- but the browser is not at
   * currentNavigationIdRef yet, so any action from here that would dispatch
   * a screen change must wait too, or the history-sync effect's next push
   * would write relative to the wrong entry and Result would never be
   * registered in history (e.g. Review -> Technical Details with no Result
   * entry between them, so Back from Technical Details lands on the
   * fail-closed Review instead of Result). Reading the ref here, inside an
   * event handler rather than during render, needs no extra React state:
   * historyCorrectionRef stays the single source of truth the popstate/sync
   * effect logic already uses, unchanged.
   */
  function handleRestart() {
    if (historyCorrectionRef.current !== null) {
      return;
    }
    dispatch({ type: "RESTART" });
  }

  function handleViewTechnicalDetails() {
    if (historyCorrectionRef.current !== null) {
      // Same guard as handleRestart above.
      return;
    }
    dispatch({ type: "OPEN_TECHNICAL_DETAILS" });
  }

  const showBackButton =
    state.screen === "compose" ||
    state.screen === "review" ||
    state.screen === "approvedReview" ||
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
            message={
              state.compose.mode === "upload"
                ? copy.processingStages.preparingDocumentReview
                : copy.processingStages.preparingReview
            }
          />
        )}

        {unrecoverableStep === null && state.screen === "review" && (
          <ReviewScreen
            preview={state.preview}
            executeError={state.executeError}
            onConfirm={() => handleConfirmReview(state)}
            onEdit={handleBack}
            examples={examples}
            compose={state.compose}
            demoTransparencyEnabled={demoTransparencyEnabled}
            demoVaultExplorerEnabled={demoVaultExplorerEnabled}
          />
        )}

        {unrecoverableStep === null && state.screen === "approvedReview" && (
          <ApprovedReviewScreen
            compose={state.compose}
            preview={state.preview}
            examples={examples}
            onGoToResult={handleForward}
          />
        )}

        {unrecoverableStep === null && state.screen === "executing" && (
          <ProcessingStatus
            message={copy.processingStages.sendConfirmed}
            detail={copy.processingStages.leavingDoesNotCancel}
          />
        )}

        {unrecoverableStep === null && state.screen === "result" && (
          <ResultScreen
            execute={state.execute}
            health={health}
            compareError={state.compareError}
            onRestart={handleRestart}
            onCompareStrategies={() => handleRequestComparison(state.compose)}
            onViewTechnicalDetails={handleViewTechnicalDetails}
            demoVaultExplorerEnabled={demoVaultExplorerEnabled}
            vaultExplorerToken={state.preview.vault_explorer_token}
          />
        )}

        {unrecoverableStep === null && state.screen === "technicalDetails" && (
          <TechnicalDetailsScreen
            execute={state.execute}
            onBack={handleBack}
          />
        )}

        {unrecoverableStep === null && state.screen === "comparing" && (
          <ProcessingStatus message={copy.processingStages.comparingStrategies} />
        )}

        {unrecoverableStep === null && state.screen === "comparison" && (
          <ComparisonScreen
            comparison={state.comparison}
            onBack={handleBack}
          />
        )}
      </main>
    </div>
  );
}
