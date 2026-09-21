/**
 * English (`en`) presentation copy -- the sibling locale to `./copy.ts`'s
 * `ptBR` (T21 / issue #29's fourth slice).
 *
 * This is a fresh, natural-English rendering of the same UI, not a
 * word-for-word translation of the Portuguese sentences -- see `copy.test.ts`
 * for the pins that keep the scientific framing intact in this language
 * specifically (CLAUDE.md warns English prose drifts toward evaluative
 * adjectives that Portuguese happened not to need pinning against):
 *
 *  - B0 is described as a baseline/reference control, never "bad", "wrong"
 *    or "worst";
 *  - B4 is described by what it does, never as "best", "most secure" or
 *    "scientifically superior" -- it may stay the recommended strategy for
 *    the demonstration flow, stated as a product/UX choice;
 *  - `strategyVsTreatmentExplanation` keeps stating, in English, that
 *    `recommended` is a request-time option that currently resolves
 *    STATICALLY to B4 -- never that a policy "chooses"/"decides" it, and
 *    never "automatically";
 *  - `timingExplanation` keeps `total_ms` framed as an operational
 *    measurement of this run, explicitly not the scientific latency metric
 *    used in the experiments.
 *
 * Scientific/internal identifiers stay OUT of this module, exactly like
 * `ptBR`: `b0`-`b4`, category identifiers, `recommended`, contract values
 * and similar are never translated -- only the prose ABOUT them lives here.
 *
 * `AppCopy` (from `./copy.ts`) is what actually enforces parity with `ptBR`:
 * a missing key, an extra key, or a wrong-shaped nested value below is a
 * compile error, not a runtime gap. See `copy.ts`'s `Widen<T>` for why that
 * type is not simply `typeof ptBR`.
 */

import type { AppCopy } from "./copy";

export const en: AppCopy = {
  howItWorks: {
    title: "How it works",
    problem: {
      heading: "Why this gateway exists",
      statement:
        "Sending a document directly to an external language model can reveal information that is not necessary for the requested task. This gateway analyzes the content locally and controls what is disclosed before any external call.",
    },
    trustBoundary: {
      heading: "The trust boundary",
      localGroupLabel: "Local environment (trusted)",
      externalGroupLabel: "Outside the trust boundary",
      diagramAlt:
        "Flow: Original document and Local gateway stay inside the trust boundary. Disclosed representation, External LLM, and Response stay outside it. Local reconstruction happens back inside the trust boundary.",
      steps: {
        originalDocument: "Original document",
        localGateway: "Local gateway",
        disclosedRepresentation: "Disclosed representation",
        externalLlm: "External LLM",
        response: "Response",
        localReconstruction: "Local reconstruction",
      },
    },
    transformations: {
      heading: "What can happen to a sensitive value",
      intro:
        "Every detected sensitive value receives one of these actions, depending on its category, the task, and the policy in force:",
      preserve: {
        label: "PRESERVE — Keep",
        description: "The value is kept unchanged because it is required for the requested task.",
        before: "Clause 4.2 of the contract",
        after: "Clause 4.2 of the contract",
      },
      remove: {
        label: "REMOVE — Remove",
        description: "The value is stripped from the content before anything is sent externally.",
        before: "SSN: 123-45-6789",
        after: "SSN: [removed]",
      },
      pseudonymize: {
        label: "PSEUDONYMIZE — Pseudonymize",
        description:
          "The value is swapped for a local pseudonym; the original never leaves the trusted environment.",
        before: "John Smith",
        after: "EMPLOYEE_A93F",
      },
      generalize: {
        label: "GENERALIZE — Generalize",
        description: "The value is swapped for a less specific version before being sent.",
        before: "$128,450.00",
        after: "Between $100,000 and $150,000",
      },
    },
    researchDisclosure: {
      intro: "The gateway implements five experimental treatments, applied in a progressive protection sequence:",
      noChoiceNeeded:
        "You do not need to choose between them: the main flow uses the recommended configuration automatically.",
    },
    ctaPrimary: "Try it now",
    ctaSecondary: "How does the research work?",
  },

  entryModes: {
    heading: "How would you like to test it?",
    useExample: "Use an example",
    uploadFile: "Upload my file",
    pasteText: "Paste text",
  },

  newTest: {
    heading: "New test",
    exampleFieldLabel: "Choose an example",
    exampleLoading: "Loading examples...",
    exampleTechnicalIdLabel: "Technical identifier for this example:",
    exampleLoadError: "Could not load the examples.",
    examplePlaceholder: "Select an example",
    pasteLabel: "Paste the text you want to test",
    pastePlaceholder: "Paste the content you want to test here.",
    uploadFieldLabel: "Choose a file",
    uploadDropHint: "Drag a PDF, DOCX, TXT, or MD contract here, or choose a file.",
    uploadUnsupportedType: "Only PDF, DOCX, TXT, or MD files are accepted.",
    uploadReadError: "Could not read the selected file.",
    removeFile: "Remove file",
    fileNameLabel: "File name",
    fileTypeLabel: "Type",
    fileSizeLabel: "Size",
    documentTypeLabel: "Document type",
    documentTypesLoading: "Loading document types...",
    documentTypesLoadError: "Could not load document types.",
    analysisModeLabel: "Analysis type",
    documentTypeLabels: {
      contract: "Contract",
      hr_record: "HR record",
    },
    analysisModeLabels: {
      contract_summary: "Contract summary",
      financial_audit: "Financial audit",
      compliance_review: "Compliance review",
      team_summary: "Team summary",
      salary_analysis: "Salary analysis",
      compensation_review: "Compensation review",
    },
    fileTypeLabels: {
      pdf: "PDF document",
      docx: "Word document",
      txt: "Plain text",
      md: "Markdown",
    },
    taskLabel: "What do you want the model to do with this content?",
    taskPlaceholder: "E.g.: Summarize the main points of this document.",
    taskHintForExample: "Leave blank to use the task suggested by the chosen example.",
    continueToReview: "Review before sending",
    incompleteHint: "Choose an example, upload a file, or paste text to continue.",
  },

  review: {
    heading: "Review before sending",
    detectedCountLabel: "sensitive items detected",
    noneDetected: "No sensitive data was detected in this content.",
    nothingInSection: "No items in this category.",
    willBeSentHeading: "What will be sent to the external LLM",
    showPayloadToggle: "View the exact payload that would be sent",
    payloadByteCountLabel: "bytes",
    blockedHeading: "Request blocked",
    blockedExplanation:
      "The disclosure policy blocked this request. Nothing will be sent to the external provider.",
    confirmSend: "Confirm and send to the external provider",
    backToCompose: "Back and edit",
    understandChangesToggle: "Understand what the gateway changed and why",
    technicalToolsToggle: "Technical details and research tools",
    technicalToolsIntro:
      "These tools exist for evaluation and research purposes. A final product would restrict or remove this layer.",
  },

  result: {
    heading: "Result",
    pathHeading: "Information path",
    pathLocal: "Local",
    pathProvider: "External provider",
    protectionsAppliedHeading: "Protections applied",
    reconstructionApplied: "Pseudonyms present in the response were replaced locally with their original values.",
    blockedHeading: "Execution blocked",
    blockedExplanation:
      "The disclosure policy blocked this execution. No content was sent to the external provider.",
    providerFailedHeading: "Provider call failed",
    providerFailedExplanation: "The external provider did not respond successfully. No answer was fabricated.",
    restart: "Test again",
    whatHappenedToggle: "Understand what happened",
    whatHappenedIntro: "See the path the information took between the local environment and the external provider.",
    researchHeading: "Compare experimental strategies (B0–B4)",
    researchIntro:
      "See how the other strategies, including the unprotected control (B0 — Direct), would have treated the same content.",
    technicalToolsHeading: "Technical details and research tools",
    technicalToolsIntro: "Execution/audit metadata and the local Vault Explorer — kept out of the main answer's way.",
  },

  provider: {
    deterministicDemoLabel: "Deterministic demonstration provider — not a real model.",
    externalModelLabel: "External model configured.",
    modeUnverifiedLabel: "Provider mode could not be verified.",
  },

  processingStages: {
    readingFile: "Reading the file",
    analyzingDocument: "Analyzing the document",
    detectingSensitiveData: "Detecting sensitive data",
    applyingDisclosurePolicy: "Applying disclosure policy",
    consultingModel: "Consulting the model",
    reconstructingAnswer: "Reconstructing the answer",
    comparingStrategies: "Comparing how each strategy would treat the same document…",
  },

  comparison: {
    surfaceLabel: "Research surface",
    heading: "How do the strategies differ?",
    intro:
      "The same content was analyzed in five different ways. Below is exactly what each one would send to the external provider.",
    simulationNotice:
      "This comparison is a disclosure simulation. None of the five strategies sends the document to the provider during this step.",
    recommendedBadge: "Strategy recommended for the demonstration flow",
    unsafeControlHeading: "Unprotected experimental control",
    unsafeControlExplanation:
      "This is the reference baseline used in the research to measure the effect of applying no protection at all. It is not a recommended option for real use, and it is never actually sent in this demonstration.",
    unsafeControlPayloadContext: "This is the content that would be sent with no protection under the reference control.",
    categoriesDetectedLabel: "sensitive categories detected",
    showPayloadToggle: "View what would be sent under this strategy",
    technicalDetailsToggle: "Technical details",
    strategyIdLabel: "Strategy identifier:",
    treatmentIdLabel: "Treatment:",
    backToResult: "Back to result",
    loadError: "Could not load the strategy comparison.",
  },

  treatments: {
    b0: {
      name: "Direct (unprotected experimental control)",
      description:
        "Sends the original content with no transformation at all. It is the research's reference control, not a recommended option for real use.",
    },
    b1: {
      name: "Static sanitization",
      description:
        "Applies a fixed, task-independent transformation to each detected sensitive item before anything is sent.",
    },
    b2: {
      name: "Reversible pseudonymization",
      description:
        "Keeps the static, local transformation. A sensitive value can be swapped for a pseudonym isolated in a local vault, which can only be reversed locally.",
    },
    b3: {
      name: "Task-aware",
      description:
        "Keeps reversible pseudonymization and chooses each category's action based on the requested task, within a fixed set of possible actions.",
    },
    b4: {
      name: "Policy-governed",
      description:
        "Keeps the previous mechanisms, but first applies a contextual organizational policy that defines what is permitted; the task can only further restrict what the policy already allows.",
    },
  } as Record<string, { name: string; description: string }>,

  technicalDetails: {
    surfaceLabel: "Technical level / audit",
    executionHeading: "Execution",
    strategyLabel: "Requested strategy",
    treatmentLabel: "Executed treatment",
    strategyVsTreatmentExplanation:
      '"Requested strategy" is the option asked for by the interface or API: it can be "recommended" or an explicit B0–B4 strategy. In the current demo configuration, "recommended" resolves to B4. "Executed treatment" shows the B0–B4 code of the treatment that actually ran. The two can differ by design; this screen draws no conclusion from either value.',

    governanceHeading: "Governance",
    domainLabel: "Domain",
    purposeLabel: "Purpose",
    policyVersionLabel: "Policy version",
    providerClassLabel: "Provider class",
    requesterRoleLabel: "Requester role",
    requestedPseudonymScopeLabel: "Requested pseudonym scope",
    notInformed: "Not provided",

    providerHeading: "Provider",
    providerNotCalledText: "The external provider was not called for this execution.",
    providerCalledLabel: "Provider called",
    providerModelIdLabel: "Model identifier",
    providerModelSnapshotLabel: "Model snapshot",
    providerDecodingConfigHeading: "Decoding configuration",
    providerDecodingConfigEmpty: "No decoding configuration was reported.",
    providerTransmittedBytesLabel: "Bytes transmitted to the provider",
    providerHashToggle: "View technical response hash (advanced metadata)",
    providerResponseHashLabel: "Technical response hash",
    providerFailedHeading: "Provider call failed",
    providerFailedExplanation:
      "The call to the external provider failed. For safety, only the failure category is shown — never the raw provider or error text.",
    providerFailureKindLabel: "Failure category",

    reconstructionHeading: "Local reconstruction",
    reconstructionExplanation:
      "Local reconstruction assembles the final answer from the provider's response while keeping the pseudonyms in the local vault. This screen never shows the pseudonym mapping or attempts to recover original values.",
    reconstructionAttemptedLabel: "Reconstruction attempted",
    reconstructionChangedLabel: "Differed from the raw provider response",
    reconstructionHashToggle: "View technical reconstruction hash (advanced metadata)",
    reconstructionHashLabel: "Technical local reconstruction hash",

    timingHeading: "Operational time",
    timingExplanation:
      "This is an operational measure of this application run — the total time, in milliseconds, elapsed for this call. It is not the scientific latency metric used in the experiments, and it should not be read as a measure of how well any strategy performed.",
    totalMsLabel: "Total time for this run",
    millisecondsUnit: "ms",

    yes: "Yes",
    no: "No",
    backToResult: "Back to result",
  },

  examplePurposes: {
    department_aggregation: "Department aggregation",
    team_summary: "Team summary",
    salary_analysis: "Salary analysis",
    compensation_review: "Compensation review",
    fitness_for_duty_review: "Fitness-for-duty review",
  } as Record<string, string>,

  categories: {
    unrecognized: "Unrecognized category",
    technicalIdLabel: "Technical identifier:",
    labels: {
      employee_name: "Employee name",
      cpf: "National ID (CPF)",
      salary: "Salary",
      department: "Department",
      medical_data: "Medical data",
      party_name: "Contract party",
      representative_name: "Representative",
      cnpj: "Company registration (CNPJ)",
      contract_value: "Contract value",
      penalty_amount: "Penalty amount",
      deadline: "Deadline",
      bank_account: "Bank account",
    },
  },

  outcomes: {
    removed: {
      label: "Removed",
      explanation: "This data was stripped from the content before anything was sent externally.",
    },
    pseudonymized: {
      label: "Replaced with a pseudonym",
      explanation:
        "The original value was swapped for a local pseudonym; the original never leaves the trusted environment.",
    },
    generalized: {
      label: "Generalized",
      explanation: "The value was swapped for a less specific version before being sent.",
    },
    preserved: {
      label: "Preserved because it is required for the task",
      explanation: "This data was kept as-is because it is required to carry out the requested task.",
    },
    blocked: {
      label: "Blocked",
      explanation: "The request was blocked and no content was sent to the external provider.",
    },
    protectedLocally: {
      label: "Protected locally",
    },
    sentToProvider: {
      label: "Sent to the model",
    },
    unknown: {
      label: "Unrecognized action — needs review",
      explanation:
        "The system returned an action this version of the interface does not recognize. For safety, it is treated as neither local nor safe until reviewed.",
      boundaryLabel: "Cannot be confirmed — needs review",
    },
  },

  buttons: {
    testNow: "Try it now",
    howResearchWorks: "How does the research work?",
    compareStrategies: "Compare strategies",
    viewTechnicalDetails: "View technical details",
    submit: "Submit",
    cancel: "Cancel",
    tryAgain: "Try again",
  },

  inspectionActions: {
    preserve: {
      label: "Preserved",
      explanation: "This segment was kept unchanged in this disclosure.",
    },
    pseudonymize: {
      label: "Pseudonymized",
      explanation: "This segment was replaced with a local pseudonym.",
    },
    generalize: {
      label: "Generalized",
      explanation: "This segment was replaced with a less specific version before being sent.",
    },
    remove: {
      label: "Removed",
      explanation: "This segment was removed and is not present in the disclosed version.",
    },
    untouched: {
      label: "Unchanged",
      explanation: "This segment was not identified as sensitive and remains the same.",
    },
    unknown: {
      label: "Unrecognized action",
      explanation:
        "The system returned an action this version of the interface does not recognize. For safety, it is not treated as any of the known actions.",
    },
    removedMarker: "[removed segment]",
  },

  disclosureInspector: {
    toggleLabel: "View side-by-side comparison (original vs. disclosed)",
    heading: "Comparison: original vs. disclosed",
    originalColumnHeading: "Original",
    disclosedColumnHeading: "Disclosed",
    legendHeading: "Action legend",
    disclaimer:
      "This transparency view exists for evaluation and research purposes. A final product would significantly restrict this feature. There is no vault explorer: this view shows only this document's own transformations.",
    unavailableBlockedHeading: "Comparison not available",
    unavailableBlockedExplanation:
      "The request was blocked by the disclosure policy, so there is no disclosed version to compare.",
    unavailableAlignmentFailedHeading: "Comparison not available for this decision",
    unavailableAlignmentFailedExplanation:
      "The alignment between the original and disclosed text could not be safely verified for this decision. The exact payload remains available above.",
    detailPanelHeading: "Selected segment detail",
    detailActionLabel: "Action:",
    detailCategoryLabel: "Category:",
    detailTreatmentLabel: "Treatment:",
    detailStrategyLabel: "Strategy:",
    detailReasonLabel: "Reason:",
    detailReasonUnavailable: "Reason not available for this category.",
    detailOriginalLabel: "Original:",
    detailDisclosedLabel: "Disclosed:",
    detailPositionLabel: "Item {n} of {total}",
    noSelectionHint: "Select a highlighted segment to see its details.",
  },

  exportRestorePanel: {
    heading: "Export and restore (demonstration)",
    disclaimer:
      "This feature exists to demonstrate the full export/restore cycle for evaluation purposes. A final product would restrict or remove this surface.",
    uploadOnlyNote: "HTTP export is available only for the file-upload flow in this demonstration.",
    exportButton: "Export",
    exportedPayloadHeading: "Exported disclosed representation",
    restorableCountLabel: "restorable items",
    expiresAtLabel: "Expires at:",
    treatmentLabel: "Treatment:",
    strategyLabel: "Strategy:",
    handleHeading: "Restore handle",
    handleHiddenNotice: "The handle is kept only on this screen, never saved automatically.",
    copyHandleButton: "Copy handle",
    copyHandleSuccess: "Handle copied.",
    downloadHandleButton: "Download handle (.txt)",
    importHandleLabel: "Import handle from a file",
    simulateResponseHeading: "Simulate external response",
    simulateResponseHint:
      "Edit the text below as if it were a response received from outside the gateway, keeping the pseudonyms you want to restore.",
    restoreButton: "Restore locally",
    restoredResultHeading: "Restore result",
    restoredCountLabel: "pseudonyms restored",
    unresolvedCountLabel: "tokens not recognized by this handle",
    unresolvedExplanation:
      "Unresolved tokens look like pseudonyms but do not belong to this restore handle's scope; they remain unchanged in the restored text.",
    clearButton: "Clear",
  },

  vaultScopes: {
    unrecognized: "Unrecognized scope",
    technicalIdLabel: "Technical identifier:",
    labels: {
      request: "A single request",
      document: "One document",
      session: "One session",
    } as Record<string, string>,
    explanations: {
      request: "This pseudonym can only be reversed within the same request that created it.",
      document: "This pseudonym can be reversed in any request about the same document.",
      session: "This pseudonym can be reversed in any request from the same session.",
    } as Record<string, string>,
  },

  vaultExplorerPanel: {
    heading: "Vault Explorer — Demonstration",
    subtitle: "Local trust boundary",
    disclaimer:
      "This view exists only for demonstration and evaluation purposes. A final product would not expose these mappings this way.",
    toggleLabel: "View the Vault Explorer (local vault)",
    unavailableForDecision: "The Vault Explorer is not available for this decision (no reference was issued).",
    loadingLabel: "Loading local vault entries...",
    scopeLabel: "Scope:",
    entryCountLabel: "reversible entries",
    zeroEntriesMessage:
      "This decision left no reversible local state: the treatment removed or generalized the sensitive data instead of pseudonymizing it.",
    categoryLabel: "Category:",
    pseudonymLabel: "What the external service received:",
    originalLabel: "What stayed inside the local boundary:",
    presentLabel: "Still held locally",
    notPresentLabel: "No longer available locally",
    showOriginalsToggle: "Show original values",
    hideOriginalsToggle: "Hide original values",
    maskedValuePlaceholder: "••••••••",
    notAvailablePlaceholder: "—",
  },

  errors: {
    generic: "The operation could not be completed. Please try again.",
    upstreamUnreachable: "Could not reach the service right now. Please try again shortly.",
    validationFailed: "The submitted data is not valid. Please review and try again.",
    fileTooLarge: "The file exceeds the limit accepted by the service.",
    documentParsing: "This document could not be processed. Check its format and try again.",
    invalidAnalysisMode: "That analysis type is not accepted for the selected document.",
    previewExpired: "This review is no longer valid. Run a new review before sending.",
    comparisonUnavailableForUpload: "Comparison is not yet available for structured documents.",
    demoTransparencyDisabled: "This demonstration feature is not enabled on this deployment.",
    exportRefused: "The export could not be generated for this content.",
    restoreUnavailable: "Local restore is not available on this deployment right now.",
    restoreHandleInvalid: "This restore handle is not valid.",
    restoreHandleExpired: "This restore handle has expired. Generate a new export.",
    demoVaultExplorerDisabled: "This demonstration feature is not enabled on this deployment.",
    vaultExplorerReferenceInvalid:
      "This local vault reference is no longer valid or has expired. Run a new review before continuing.",
  },

  sectionHeadings: {
    whatWasDetected: "What was detected",
    whatStaysLocal: "What stays local",
    whatWasSent: "What was sent",
    finalAnswer: "Final answer",
    technicalDetails: "Technical details",
    compareStrategies: "Compare strategies",
  },

  theme: {
    light: "Light",
    dark: "Dark",
    system: "Automatic (system)",
    toggleLabel: "Theme",
  },

  language: {
    toggleLabel: "Language",
  },
};
