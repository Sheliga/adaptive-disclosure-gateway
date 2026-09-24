/**
 * Centralized user-facing copy. This module is the ONE place presentation
 * prose lives -- every string a component renders must come from here (or
 * its sibling locale module), never inlined in a component.
 *
 * Scientific/internal identifiers (`b0`-`b4`, `removed`, `pseudonymized`,
 * example/category codes, contract versions, ...) are DELIBERATELY absent
 * from this module: CLAUDE.md and issue #29 both pin those as verbatim
 * data, never translated. This module only ever holds presentation prose
 * *about* those identifiers, never the identifiers themselves.
 *
 * --- How the second locale was added (T21 fourth slice / #29) ---
 *
 * 1. `AppCopy` is derived structurally from `ptBR` via `Widen<typeof ptBR>`
 *    (below) rather than `typeof ptBR` directly. Plain `typeof ptBR` would
 *    produce LITERAL string types (`title: "Como funciona"`), because the
 *    object below ends in `as const` -- so a second locale would be forced
 *    to contain the identical Portuguese strings to type-check. `Widen`
 *    recursively replaces every literal string (and the contents of every
 *    array) with `string`, while preserving the exact key structure, so
 *    `AppCopy` enforces "same shape" without demanding "same words".
 * 2. `./copy.en.ts` defines `export const en: AppCopy = { ... }` in its
 *    own module -- TypeScript's structural typing against `AppCopy` means a
 *    missing key, an extra key, or a wrong-shaped nested value is a compile
 *    error in that file, not a silent runtime gap.
 * 3. `resolveCopy(locale)` below picks between `ptBR` and `en`; the
 *    persisted user preference that calls it lives in `web/i18n/`
 *    (`LocaleProvider`/`useLocale`), never read directly by a component.
 *
 * `copy` (the flat, non-resolved export) is kept as the pt-BR table --
 * `resolveCopy(DEFAULT_LOCALE)` -- for callers that have no locale context
 * of their own (a handful of pure `lib/*.ts` helpers take an explicit
 * `AppCopy` parameter defaulting to this), and so this module's existing
 * behavior does not change unless a caller opts into locale switching.
 */

import type { Locale } from "@/i18n/locales";

import { en } from "./copy.en";

const ptBR = {
  howItWorks: {
    title: "Como funciona",
    /**
     * T30 / issue #82: the problem statement a first-time visitor (a
     * prospective advisor) must read BEFORE any mechanism explanation --
     * why the gateway exists, in plain language, with no project
     * vocabulary.
     */
    problem: {
      heading: "Por que este gateway existe",
      statement:
        "Enviar um documento diretamente a um modelo de linguagem externo pode revelar informações que não são necessárias para a tarefa pedida. Este gateway analisa o conteúdo localmente e controla o que é divulgado antes de qualquer chamada externa.",
    },
    /**
     * T30 / issue #82: the visual trust-boundary flow diagram. `steps` is
     * an OBJECT (not an array) keyed by a stable identifier, because each
     * step also needs a `zone` (local/external) assignment in the
     * component -- the identifier is what ties the copy value to that
     * zone, whereas an array index would silently break if a step were
     * ever reordered here without the component's zone list changing too.
     */
    trustBoundary: {
      heading: "A fronteira de confiança",
      localGroupLabel: "Ambiente local (confiável)",
      externalGroupLabel: "Fora da fronteira de confiança",
      diagramAlt:
        "Fluxo: Documento original e Gateway local ficam dentro da fronteira de confiança. Representação divulgada, LLM externo e Resposta ficam fora dela. A Reconstrução local volta a acontecer dentro da fronteira de confiança.",
      steps: {
        originalDocument: "Documento original",
        localGateway: "Gateway local",
        disclosedRepresentation: "Representação divulgada",
        externalLlm: "LLM externo",
        response: "Resposta",
        localReconstruction: "Reconstrução local",
      },
    },
    /**
     * T30 / issue #82: PRESERVE/REMOVE/PSEUDONYMIZE/GENERALIZE explained at
     * the CONCEPT level, with tiny synthetic before->after examples --
     * deliberately no vault/scope vocabulary here (that stays in technical
     * details/the Vault Explorer). The label keeps the frozen English
     * action word visible (matching `lib/inspectionActions.ts`'s own
     * frozen action codes elsewhere in the app) alongside a translated
     * verb, since a reviewer who later opens the transformation inspector
     * should recognize the same vocabulary.
     */
    transformations: {
      heading: "O que pode acontecer com um dado sensível",
      intro:
        "Cada dado sensível detectado recebe uma destas ações, dependendo da categoria, da tarefa e da política vigente:",
      preserve: {
        label: "PRESERVE — Manter",
        description: "O valor é mantido sem alteração porque é necessário para a tarefa pedida.",
        before: "Cláusula 4.2 do contrato",
        after: "Cláusula 4.2 do contrato",
      },
      remove: {
        label: "REMOVE — Remover",
        description:
          "O valor é retirado do conteúdo antes de qualquer envio externo; nada é colocado no lugar dele.",
        before: "CPF: 123.456.789-00",
        after: "CPF:",
      },
      pseudonymize: {
        label: "PSEUDONYMIZE — Pseudonimizar",
        description:
          "O valor é trocado por um pseudônimo local; o original nunca sai do ambiente confiável.",
        before: "João da Silva",
        after: "PSEUDO-employee_name-a1c2d3e4f5061728394a5c6d7e8f9012",
      },
      generalize: {
        label: "GENERALIZE — Generalizar",
        description: "O valor é trocado por uma versão menos específica antes do envio.",
        before: "R$ 128.450,00",
        after: "R$ 125000-130000",
      },
    },
    /**
     * T30 / issue #82: the collapsible "Como funciona a pesquisa?" section
     * -- the ONLY place on the welcome screen where B0-B4 vocabulary may
     * appear, closed by default. `treatments` (already defined below,
     * keyed by the frozen `b0`-`b4` code) supplies the per-treatment
     * name/description; this table only holds the framing prose around it.
     */
    researchDisclosure: {
      intro:
        "O gateway implementa cinco tratamentos experimentais, aplicados numa sequência progressiva de proteção:",
      noChoiceNeeded:
        "Você não precisa escolher entre eles: o fluxo principal usa a configuração recomendada automaticamente.",
    },
    ctaPrimary: "Testar agora",
    ctaSecondary: "Como funciona a pesquisa?",
  },

  entryModes: {
    heading: "Como você quer testar?",
    useExample: "Usar um exemplo",
    uploadFile: "Enviar meu arquivo",
    pasteText: "Colar texto",
  },

  /** Screen 2 -- "Novo teste": entry mode fields, upload UX, task field. */
  newTest: {
    heading: "Novo teste",
    exampleFieldLabel: "Escolha um exemplo",
    exampleLoading: "Carregando exemplos...",
    exampleTechnicalIdLabel: "Identificador técnico deste exemplo:",
    exampleLoadError: "Não foi possível carregar os exemplos.",
    examplePlaceholder: "Selecione um exemplo",
    pasteLabel: "Cole o texto que deseja testar",
    pastePlaceholder: "Cole aqui o conteúdo que deseja testar.",
    uploadFieldLabel: "Selecione um arquivo",
    uploadDropHint: "Arraste um contrato PDF, DOCX, TXT ou MD aqui, ou escolha um arquivo.",
    uploadUnsupportedType: "Apenas arquivos PDF, DOCX, TXT ou MD são aceitos.",
    uploadReadError: "Não foi possível ler o arquivo selecionado.",
    removeFile: "Remover arquivo",
    fileNameLabel: "Nome do arquivo",
    fileTypeLabel: "Tipo",
    fileSizeLabel: "Tamanho",
    documentTypeLabel: "Tipo de documento",
    documentTypesLoading: "Carregando tipos de documento...",
    documentTypesLoadError: "Não foi possível carregar os tipos de documento.",
    analysisModeLabel: "Tipo de análise",
    documentTypeLabels: {
      contract: "Contrato",
      hr_record: "Registro de RH",
    } as Record<string, string>,
    analysisModeLabels: {
      contract_summary: "Resumo do contrato",
      financial_audit: "Auditoria financeira",
      compliance_review: "Revisão de conformidade",
      team_summary: "Resumo da equipe",
      salary_analysis: "Análise salarial",
      compensation_review: "Revisão de remuneração",
    } as Record<string, string>,
    fileTypeLabels: {
      pdf: "Documento PDF",
      docx: "Documento Word",
      txt: "Texto simples",
      md: "Markdown",
    } as Record<string, string>,
    taskLabel: "O que você quer que o modelo faça com esse conteúdo?",
    taskPlaceholder: "Ex.: Resuma os pontos principais deste documento.",
    taskHintForExample: "Deixe em branco para usar a tarefa sugerida pelo exemplo escolhido.",
    continueToReview: "Revisar antes de enviar",
    incompleteHint: "Escolha um exemplo, envie um arquivo ou cole um texto para continuar.",
  },

  /** Screen 3 -- "Revisão antes do envio". */
  review: {
    heading: "Revisão antes do envio",
    detectedCountLabel: "itens sensíveis detectados",
    noneDetected: "Nenhum dado sensível foi detectado neste conteúdo.",
    nothingInSection: "Nenhum item nesta categoria.",
    /**
     * T30 / issue #82: the heading over the "exactly what crosses the
     * boundary" section -- deliberately forward-looking ("será enviado"),
     * unlike `sectionHeadings.whatWasSent` (used by the Comparação screen,
     * which describes a simulation of five already-computed strategies).
     * This is the prominent, unambiguously-labelled disclosure the review
     * step's confirm decision hinges on.
     */
    willBeSentHeading: "O que será enviado ao LLM externo",
    showPayloadToggle: "Ver o payload exato que seria enviado",
    payloadByteCountLabel: "bytes",
    blockedHeading: "Solicitação bloqueada",
    blockedExplanation:
      "A política de divulgação bloqueou esta solicitação. Nada será enviado ao provedor externo.",
    /**
     * T30 / issue #82: states the consequence explicitly, not just the
     * mechanical action -- the primary decision this screen exists for.
     */
    confirmSend: "Confirmar e enviar ao provedor externo",
    /**
     * T32.2 / #102: the irreversible boundary, stated in plain language right
     * next to the CTA -- confirming is what starts the external call, and
     * once it has started, navigating away does not cancel or undo it.
     */
    confirmConsequence: "Ao confirmar, a solicitação é enviada ao provedor externo.",
    afterSendNotice:
      "Depois que o envio começar, voltar ou sair desta tela não cancela nem desfaz o envio.",
    /** Shown under an execute error: a new attempt is only ever the user's explicit choice. */
    executeErrorNoAutoRetry:
      "Nada é reenviado automaticamente. Para tentar novamente, confirme outra vez.",
    /**
     * T32.2 / #102: "What you asked for" -- re-presents the retained compose
     * context before any disclosure detail, so the reviewer does not have to
     * remember what they chose on the previous screen.
     */
    contextHeading: "O que você pediu",
    sourceLabel: "Origem",
    sourceExample: "Exemplo preparado",
    sourceUpload: "Arquivo enviado",
    sourcePaste: "Texto colado",
    exampleLabel: "Exemplo",
    taskLabel: "Tarefa",
    exampleSuggestedTask: "(tarefa sugerida pelo exemplo)",
    noTaskProvided: "Nenhuma tarefa informada",
    /** Fail-closed label for any value this UI has no human copy for. */
    unknownValue: "Não identificado",
    /** Returns to the existing Compose snapshot (browser history), every field preserved. */
    changeRequest: "Alterar dados da solicitação",
    /**
     * T30 / issue #82: Level-2 disclosure wrapping the T27 transformation
     * inspector -- "understand what changed and why" sits one level below
     * the plain-language local/sent lists.
     */
    understandChangesToggle: "Ver a explicação detalhada das transformações",
    /**
     * T30 / issue #82: Level-3 disclosure wrapping the T28 export/restore
     * panel and the T29 Vault Explorer -- collapsed by default, framed
     * explicitly as a research/technical surface, not part of the primary
     * decision.
     */
    technicalToolsToggle: "Detalhes técnicos e ferramentas de pesquisa",
    technicalToolsIntro:
      "Estas ferramentas existem para avaliação e pesquisa. Um produto final restringiria ou removeria esta camada.",
  },

  /**
   * T32.2 / #102: the read-only Review a confirmed send came from, reachable
   * only through history (Result -> Back). It never offers Confirm, resend or
   * Change, and says plainly that looking at it does not undo the send.
   * "Envio já confirmado" rather than "enviado": a send can still end up
   * blocked or failed at execute time, but it was confirmed either way.
   */
  approvedReview: {
    heading: "Revisão aprovada",
    sentBadge: "Envio já confirmado",
    readOnlyNotice:
      "Esta é a revisão que você aprovou antes do envio. Ela é somente leitura: visualizá-la não desfaz nem repete o envio.",
    sentHeading: "O que foi aprovado para envio ao LLM externo",
    payloadToggle: "Ver o payload exato aprovado para envio",
    goToResult: "Ir para o resultado",
  },

  /** Screen 4 -- "Resultado". */
  result: {
    heading: "Resultado",
    pathHeading: "Caminho da informação",
    pathLocal: "Local",
    pathProvider: "Provedor externo",
    protectionsAppliedHeading: "Proteções aplicadas",
    /**
     * T30 / issue #82 review follow-up (Finding 1): the previous single
     * headline ("N itens protegidos") summed `occurrence_count` over EVERY
     * category, including `preserved` ones (sent unchanged) and unknown
     * outcomes -- both false "protected" claims. Replaced with a per-action
     * breakdown built from `describeCategoryOutcome`'s own fail-closed
     * label (see `ResultScreen`'s `buildProtectionsBreakdown`), so a
     * preserved-only or unknown-only execution never claims protection it
     * did not provide.
     */
    reconstructionApplied: "Pseudônimos presentes na resposta foram substituídos localmente pelos valores originais.",
    blockedHeading: "Execução bloqueada",
    blockedExplanation:
      "A política de divulgação bloqueou esta execução. Nenhum conteúdo foi enviado ao provedor externo.",
    providerFailedHeading: "Falha ao consultar o provedor",
    providerFailedExplanation:
      "O provedor externo não respondeu com sucesso. Nenhuma resposta foi fabricada.",
    restart: "Testar novamente",
    /**
     * T30 / issue #82: Level-2 disclosure wrapping the Local -> Provedor
     * externo -> Local recap -- explanatory content, secondary to the
     * answer and the protections summary.
     */
    whatHappenedToggle: "Entender o que aconteceu",
    whatHappenedIntro: "Veja o caminho que a informação percorreu entre o ambiente local e o provedor externo.",
    /**
     * T30 / issue #82: frames "Comparar estratégias" explicitly as a
     * research surface rather than a plain secondary action.
     */
    researchHeading: "Comparar estratégias experimentais (B0–B4)",
    researchIntro:
      "Veja como as outras estratégias, incluindo o controle sem proteção (B0 — Direto), teriam tratado o mesmo conteúdo.",
    /**
     * T30 / issue #82: frames "Ver detalhes técnicos" and the Vault
     * Explorer as the technical/audit layer, secondary to the primary
     * result.
     */
    technicalToolsHeading: "Detalhes técnicos e ferramentas de pesquisa",
    technicalToolsIntro:
      "Metadados de execução, auditoria e o Vault Explorer local -- não competem com a resposta principal.",
  },

  provider: {
    deterministicDemoLabel: "Provedor de demonstração determinístico — não é um modelo real.",
    externalModelLabel: "Modelo externo configurado.",
    /*
     * Shown when `GET /health` could not be reached or did not satisfy its
     * contract. Deliberately states only that the check failed -- it must
     * not read as "this is the demo provider" (a claim nothing verified)
     * nor be omitted (which reads as the verified real-provider case). See
     * lib/providerMode.ts.
     */
    modeUnverifiedLabel: "Modo do provedor não pôde ser verificado.",
  },

  /**
   * T32.2 / #102: honest async states. The frontend has no backend progress
   * telemetry, so each wait is ONE general message -- never a sequence of
   * sub-stages that would imply observed progress it does not have.
   */
  processingStages: {
    preparingReview: "Preparando a revisão…",
    preparingDocumentReview: "Processando o documento e preparando a revisão…",
    sendConfirmed: "Envio confirmado. A solicitação está sendo processada.",
    leavingDoesNotCancel: "Sair desta etapa não cancela uma chamada externa já iniciada.",
    /**
     * Deliberately does NOT say "consultando cinco modelos" or anything
     * implying five provider calls happen -- the comparison never calls a
     * provider for any strategy (see `copy.comparison.simulationNotice`).
     */
    comparingStrategies: "Comparando como cada estratégia trataria o mesmo documento…",
  },

  /**
   * Screen "Comparação B0-B4" -- T21 / issue #29's second slice. Reached
   * from Result via `buttons.compareStrategies`; consumes
   * `POST /disclosure/compare` (`lib/api.ts`'s `compareStrategies`).
   *
   * `simulationNotice` is the single most important string here: the
   * comparison is preview-only for every strategy, including B0 -- Direct,
   * and this is the one place that fact is stated to the reviewer in plain
   * language rather than left implicit.
   */
  comparison: {
    /**
     * T30 / issue #82: a short eyebrow label framing this whole screen as
     * a research surface, rendered above `heading`.
     */
    surfaceLabel: "Superfície de pesquisa",
    heading: "Como as estratégias diferem?",
    intro:
      "O mesmo conteúdo foi analisado de cinco maneiras diferentes. A seguir está exatamente o que cada uma enviaria ao provedor externo.",
    simulationNotice:
      "Esta comparação é uma simulação de divulgação. Nenhuma das cinco estratégias envia o documento ao provedor durante esta etapa.",
    recommendedBadge: "Estratégia recomendada para o fluxo demonstrativo",
    unsafeControlHeading: "Controle experimental sem proteção",
    unsafeControlExplanation:
      "Esta é a estratégia de referência usada na pesquisa para medir o efeito de não aplicar nenhuma proteção. Ela não é uma opção recomendada para uso real e nunca é enviada de fato nesta demonstração.",
    unsafeControlPayloadContext:
      "Este é o conteúdo que seria enviado sem proteção no controle de referência.",
    categoriesDetectedLabel: "categorias sensíveis detectadas",
    showPayloadToggle: "Ver o que seria enviado nesta estratégia",
    technicalDetailsToggle: "Detalhes técnicos",
    strategyIdLabel: "Identificador da estratégia:",
    treatmentIdLabel: "Tratamento:",
    backToResult: "Voltar ao resultado",
    loadError: "Não foi possível carregar a comparação entre estratégias.",
  },

  /**
   * Short, plain-language descriptions of each treatment for the
   * comparison screen, keyed by the FROZEN `b0`-`b4` strategy code -- same
   * split as `categories.labels`/`examplePurposes` above: the key is a
   * verbatim identifier from the API/domain, never translated; only the
   * value is presentation prose. Derived from `docs/experimental-design.md`
   * ("Treatment definitions"), not from a paraphrase of it -- e.g. B0 is
   * that document's own "unsafe control treatment" language, and B4's
   * description mirrors its "policy resolves the permitted action space
   * first" ordering claim. `name` is a human name; the `b0`-`b4` code and
   * the raw `treatment` string stay in the expandable technical-details
   * area (see `ComparisonScreen`), never in this prose.
   */
  treatments: {
    b0: {
      name: "Direto (controle experimental sem proteção)",
      description:
        "Envia o conteúdo original sem nenhuma transformação. É o controle de referência da pesquisa, não uma opção recomendada para uso real.",
    },
    b1: {
      name: "Sanitização estática",
      description:
        "Aplica uma transformação fixa e independente da tarefa a cada dado sensível detectado, antes de qualquer envio.",
    },
    b2: {
      name: "Pseudonimização reversível",
      description:
        "Mantém a transformação estática e local. Um dado sensível pode ser trocado por um pseudônimo isolado em um cofre local, que só pode ser revertido localmente.",
    },
    b3: {
      name: "Consciente da tarefa",
      description:
        "Mantém a pseudonimização reversível e escolhe a ação de cada categoria considerando a tarefa pedida, dentro de um conjunto fixo de ações possíveis.",
    },
    b4: {
      name: "Governança por política",
      description:
        "Mantém os mecanismos anteriores, mas primeiro aplica uma política organizacional contextual que define o que é permitido; a tarefa só pode restringir ainda mais dentro do que a política já permite.",
    },
  } as Record<string, { name: string; description: string }>,

  /**
   * Screen "Detalhes técnicos" -- T21 / issue #29's third slice. Reached
   * from Resultado via `buttons.viewTechnicalDetails`; renders operational
   * metadata already present on the SAME `ExecuteResponse` Resultado holds
   * -- no new request, no scientific metric, no re-run of anything.
   *
   * `strategyVsTreatmentExplanation` is the one interpretive sentence this
   * screen adds: `strategy` is the interface/API choice the request asked
   * for -- `application/contracts.py`'s `DisclosureStrategy` admits
   * `recommended` AND each explicit `b0`-`b4` code, so an explicit B0-B4
   * strategy is perfectly legal here, not just `"recommended"`. `treatment`
   * is the `b0`-`b4` code of what the pipeline actually executed.
   * `_STRATEGY_TO_TREATMENT` is a static dict, not a decision procedure:
   * every explicit strategy maps to the treatment it names, and only
   * `RECOMMENDED` maps (today, as a product/UX default for the guided demo)
   * to `Treatment.POLICY_GOVERNED` -- nothing is resolved dynamically, and
   * nothing inspects the document or the policy engine to pick a treatment.
   * Stating the distinction is not the same as drawing a conclusion from it
   * -- this screen draws none, never claims B4 is scientifically better,
   * and never renders either value as a comparison/ranking code.
   *
   * `providerHashToggle`/`reconstructionHashToggle` keep `response_hash`/
   * `reconstructed_hash` behind their own expandable disclosure, one level
   * deeper than the rest of the safe metadata -- CLAUDE.md's no-leak
   * invariant treats a public, reproducible digest of low-entropy content as
   * guessable/dictionary-reversible, so these are presented as opaque
   * technical metadata, never as content to inspect casually.
   */
  technicalDetails: {
    /**
     * T30 / issue #82: a short eyebrow label framing this whole screen as
     * the technical/audit level, rendered above the screen heading.
     */
    surfaceLabel: "Nível técnico / auditoria",
    executionHeading: "Execução",
    strategyLabel: "Estratégia solicitada",
    treatmentLabel: "Tratamento executado",
    strategyVsTreatmentExplanation:
      '"Estratégia solicitada" é a opção pedida pela interface ou API: pode ser "recommended" ou uma estratégia B0–B4 explícita. Na configuração atual da demonstração, "recommended" resolve para B4. "Tratamento executado" mostra o código B0–B4 do tratamento que efetivamente rodou. Os dois podem ser diferentes por design; esta tela não tira nenhuma conclusão a partir de nenhum dos dois valores.',

    governanceHeading: "Governança",
    domainLabel: "Domínio",
    purposeLabel: "Finalidade",
    policyVersionLabel: "Versão da política",
    providerClassLabel: "Classe do provedor",
    requesterRoleLabel: "Papel do solicitante",
    requestedPseudonymScopeLabel: "Escopo de pseudonimização solicitado",
    notInformed: "Não informado",

    providerHeading: "Provedor",
    providerNotCalledText: "O provedor externo não foi chamado nesta execução.",
    providerCalledLabel: "Provedor chamado",
    providerModelIdLabel: "Identificador do modelo",
    providerModelSnapshotLabel: "Snapshot do modelo",
    providerDecodingConfigHeading: "Configuração de decodificação",
    providerDecodingConfigEmpty: "Nenhuma configuração de decodificação informada.",
    providerTransmittedBytesLabel: "Bytes transmitidos ao provedor",
    providerHashToggle: "Ver hash técnico da resposta (metadado avançado)",
    providerResponseHashLabel: "Hash técnico da resposta",
    providerFailedHeading: "Falha na chamada ao provedor",
    providerFailedExplanation:
      "A chamada ao provedor externo falhou. Por segurança, apenas a categoria da falha é exibida — nunca o texto bruto do provedor ou do erro.",
    providerFailureKindLabel: "Categoria da falha",

    reconstructionHeading: "Reconstrução local",
    reconstructionExplanation:
      "A reconstrução local recompõe a resposta final a partir da resposta do provedor mantendo os pseudônimos no cofre local. Esta tela nunca exibe o mapeamento de pseudônimos nem tenta recuperar valores originais.",
    reconstructionAttemptedLabel: "Reconstrução tentada",
    reconstructionChangedLabel: "Divergiu da resposta bruta do provedor",
    reconstructionHashToggle: "Ver hash técnico da reconstrução (metadado avançado)",
    reconstructionHashLabel: "Hash técnico da reconstrução local",

    timingHeading: "Tempo operacional",
    timingExplanation:
      "Esta é uma medida operacional desta execução da aplicação — o tempo total, em milissegundos, decorrido nesta chamada. Não é a métrica científica de latência usada nos experimentos e não deve ser interpretada como uma pontuação de desempenho.",
    totalMsLabel: "Tempo total desta execução",
    millisecondsUnit: "ms",

    yes: "Sim",
    no: "Não",
    backToResult: "Voltar ao resultado",
  },

  /**
   * pt-BR labels for the prepared examples' `purpose` values -- the only
   * human-readable thing the API gives us about an example besides its raw
   * corpus sample id (see lib/exampleLabels.ts for why the label is derived
   * here rather than server-side).
   *
   * Keys are the frozen `purpose` identifiers exactly as the corpus and
   * the policy matrix spell them -- never translated, never renamed. A
   * purpose with no entry here deliberately falls back to the raw id rather
   * than to an invented label.
   */
  examplePurposes: {
    department_aggregation: "Agregação por departamento",
    team_summary: "Resumo de equipe",
    salary_analysis: "Análise salarial",
    compensation_review: "Revisão de remuneração",
    fitness_for_duty_review: "Avaliação de aptidão para o trabalho",
  } as Record<string, string>,

  /**
   * pt-BR labels for the sensitive-data CATEGORIES the API reports back on
   * each `CategoryDisclosureSummary`.
   *
   * Same split as `examplePurposes` above and for the same reason: the keys
   * are the frozen policy identifiers exactly as `configs/policies/hr-v1`,
   * `hr-v2` and `hr-v3` spell them, and nothing here renames, translates or
   * reorders anything on the API side -- `category.category` keeps carrying
   * `employee_name` verbatim through the contract, the outcome mapping and
   * the React key. Only the string the reviewer READS comes from here.
   *
   * Why it is needed: T21's primary flow is novice-first (issue #29 -- "a
   * reviewer unfamiliar with the project can understand ... without
   * external documentation"). `employee_name` / `medical_data` as the
   * headline of a row on the consent screen is a scientific identifier
   * doing a product's job.
   *
   * `unrecognized` is the fail-closed presentation, NOT a fallback label: a
   * category with no entry here is explicitly marked unrecognized rather
   * than prettified from its identifier. See `lib/categoryLabels.ts` for
   * why an invented-but-confident label is the worse failure on a
   * disclosure demo.
   */
  categories: {
    unrecognized: "Categoria não reconhecida",
    technicalIdLabel: "Identificador técnico:",
    labels: {
      employee_name: "Nome do funcionário",
      cpf: "CPF",
      salary: "Salário",
      department: "Departamento",
      medical_data: "Dados médicos",
      party_name: "Parte do contrato",
      representative_name: "Representante",
      cnpj: "CNPJ",
      contract_value: "Valor do contrato",
      penalty_amount: "Multa / penalidade",
      deadline: "Prazo",
      bank_account: "Conta bancária",
    },
  },

  /**
   * Per category disclosure outcome: the "what happened" label/explanation
   * pairs, plus the trust-boundary pair used independently of outcome (see
   * `outcomes.ts`, which reads `crosses_trust_boundary` directly rather
   * than guessing it from these labels).
   */
  outcomes: {
    removed: {
      label: "Removido",
      explanation: "Esse dado foi retirado do conteúdo antes de qualquer envio externo.",
    },
    pseudonymized: {
      label: "Substituído por pseudônimo",
      explanation:
        "O valor original foi trocado por um pseudônimo local; o original nunca sai do ambiente confiável.",
    },
    generalized: {
      label: "Generalizado",
      explanation: "O valor foi trocado por uma versão menos específica antes do envio.",
    },
    preserved: {
      label: "Mantido porque é necessário para a tarefa",
      explanation: "Esse dado foi mantido como está por ser necessário para realizar a tarefa pedida.",
    },
    blocked: {
      label: "Bloqueado",
      explanation: "A solicitação foi bloqueada e nenhum conteúdo foi enviado ao provedor externo.",
    },
    protectedLocally: {
      label: "Protegido localmente",
    },
    sentToProvider: {
      label: "Enviado ao modelo",
    },
    unknown: {
      label: "Ação não reconhecida — requer revisão",
      explanation:
        "O sistema retornou uma ação que esta versão da interface não reconhece. Por segurança, ela não é tratada como local nem como segura até ser revisada.",
      boundaryLabel: "Não é possível confirmar — requer revisão",
    },
  },

  buttons: {
    testNow: "Testar agora",
    howResearchWorks: "Como funciona a pesquisa?",
    compareStrategies: "Comparar estratégias",
    viewTechnicalDetails: "Ver detalhes técnicos",
    submit: "Enviar",
    cancel: "Cancelar",
    tryAgain: "Tentar novamente",
  },

  /**
   * T32.3 / #103: the primary before/after ("O que o gateway fez"), built
   * only from `preview.inspection.segments` -- visible by default in Review
   * and in the Approved Review, and as a recap in Result. Answers only what
   * was there, what changed and what was prepared for disclosure; technical
   * reasons, treatment, strategy and ids stay in the detailed inspector.
   * `{n}` is a plain count.
   *
   * IDENTITY CAVEAT (fix for #103 review, see PR #108): this block never
   * claims the disclosed side is byte-identical to what LATER crosses the
   * boundary at execute time. That is only structurally guaranteed for
   * upload, where `execute_document` is confirmation-token-bound to this
   * exact preview. For paste/example, `executeDisclosure` re-runs the
   * decision (detector, task analyzer, decision phase) independently of the
   * preview shown here, so the copy says "prepared"/"reviewed", never
   * "exactly what is sent" or "exactly what crosses the boundary".
   */
  beforeAfter: {
    heading: "O que o gateway fez",
    intro:
      "Antes de qualquer envio, o gateway transformou localmente os trechos destacados. Primeiro, o que você enviou; depois, a representação preparada para o modelo externo.",
    originalHeading: "Original",
    originalCaption: "O conteúdo que você enviou ao gateway. Ele não sai daqui.",
    transformationStep: "Transformação local no gateway",
    disclosedHeadingReview: "Representação preparada para envio ao modelo externo",
    disclosedCaptionReview:
      "Esta é a representação que o gateway preparou para divulgação externa nesta revisão, antes da sua confirmação.",
    disclosedHeadingApproved: "Representação aprovada antes do envio",
    disclosedCaptionApproved:
      "Esta foi a representação apresentada para sua aprovação antes da chamada externa.",
    handledCount: "Trechos tratados pelo gateway: {n}",
    noChanges: "O gateway não precisou alterar nenhum trecho: o texto foi preparado para envio sem alterações.",
    unavailableBlocked:
      "Nenhuma representação foi liberada para envio: a solicitação foi bloqueada no gateway e nada sai para o modelo externo.",
    unavailableAlignmentFailed:
      "A transformação foi aplicada, mas a visualização detalhada de antes/depois não pôde ser produzida com segurança.",
    unavailableUnknown: "A visualização de antes/depois não está disponível para esta solicitação.",
  },

  /**
   * T32.3 / #103: the short Result recap -- which transformation this answer
   * came after. Wording is chosen from `ExecuteResponse.provider`: never
   * "sent"/"consulted" when `provider.called` is false, and a failed call
   * is described as an attempt, not a consultation that produced an answer.
   *
   * IDENTITY CAVEAT (fix for #103 review, see PR #108): `sent` describes the
   * transformation the reviewer approved and the fact that the external
   * model was then consulted -- it does not assert that the previewed
   * representation is byte-identical to what `execute` actually sent (true
   * only for upload; paste/example recompute the decision at execute time).
   */
  resultRecap: {
    heading: "O que aconteceu antes do envio",
    sent:
      "Antes da chamada externa, você revisou esta transformação feita pelo gateway. O modelo externo foi consultado e esta é a resposta reconstruída localmente.",
    providerFailed:
      "O gateway transformou localmente o seu conteúdo e tentou consultar o modelo externo, mas a consulta falhou: nenhuma resposta foi produzida.",
    notSent:
      "O gateway preparou a representação transformada, mas nada foi enviado: o modelo externo não foi consultado.",
    handledCount: "Trechos tratados pelo gateway antes da fronteira externa: {n}",
    seeBeforeAfter: "Ver o antes/depois aprovado na revisão",
  },

  /**
   * T27 / issue #69: per-action descriptors for the transformation inspector
   * (`lib/inspectionActions.ts`). Keyed by the FROZEN `DisclosureAction`
   * codes (`preserve`, `pseudonymize`, `generalize`, `remove`) -- same split
   * as `outcomes` above: the key is verbatim API vocabulary, never
   * translated, only the value is presentation prose. Deliberately a
   * SEPARATE table from `outcomes` even though the underlying concepts are
   * closely related (an outcome is what a category ended up as; an
   * inspector action is what happened to one specific segment of text) --
   * this table's copy is written for the segment-level, click-to-inspect
   * context, `outcomes`'s for the category-summary context, and the two are
   * free to diverge in wording without either module having to know about
   * the other's copy.
   */
  inspectionActions: {
    preserve: {
      label: "Mantido",
      explanation: "Este trecho foi mantido sem alteração nesta divulgação.",
    },
    pseudonymize: {
      label: "Pseudonimizado",
      explanation: "Este trecho foi substituído por um pseudônimo local.",
    },
    generalize: {
      label: "Generalizado",
      explanation: "Este trecho foi substituído por uma versão menos específica antes do envio.",
    },
    remove: {
      label: "Removido",
      explanation: "Este trecho foi removido e não está presente na versão divulgada.",
    },
    untouched: {
      label: "Sem alteração",
      explanation: "Este trecho não foi identificado como sensível e permanece igual.",
    },
    unknown: {
      label: "Ação não reconhecida",
      explanation:
        "O sistema retornou uma ação que esta versão da interface não reconhece. Por segurança, ela não é tratada como nenhuma das ações conhecidas.",
    },
    removedMarker: "[trecho removido]",
  },

  /**
   * T27 / issue #69: the transformation inspector itself
   * (`components/DisclosureInspector/`), rendered inside `ReviewScreen` only
   * when `preview.inspection !== null`.
   */
  disclosureInspector: {
    toggleLabel: "Ver comparação lado a lado (original x divulgado)",
    heading: "Comparação: original x divulgado",
    originalColumnHeading: "Original",
    disclosedColumnHeading: "Divulgado",
    legendHeading: "Legenda das ações",
    disclaimer:
      "Esta visão de transparência existe para fins de avaliação e pesquisa. Um produto final restringiria significativamente este recurso. Não existe um explorador de cofre: esta visão mostra apenas as transformações deste documento.",
    unavailableBlockedHeading: "Comparação não disponível",
    unavailableBlockedExplanation:
      "A solicitação foi bloqueada pela política de divulgação, então não há uma versão divulgada para comparar.",
    unavailableAlignmentFailedHeading: "Comparação não disponível para esta decisão",
    unavailableAlignmentFailedExplanation:
      "Não foi possível verificar com segurança o alinhamento entre o texto original e o divulgado para esta decisão. O payload exato continua disponível acima.",
    detailPanelHeading: "Detalhe do trecho selecionado",
    detailActionLabel: "Ação:",
    detailCategoryLabel: "Categoria:",
    detailTreatmentLabel: "Tratamento:",
    detailStrategyLabel: "Estratégia:",
    detailReasonLabel: "Motivo:",
    detailReasonUnavailable: "Motivo não disponível para esta categoria.",
    detailOriginalLabel: "Original:",
    detailDisclosedLabel: "Divulgado:",
    detailPositionLabel: "Item {n} de {total}",
    noSelectionHint: "Selecione um trecho destacado para ver os detalhes.",
  },

  /**
   * T28 / issue #70: the export/restore demonstration panel
   * (`components/ExportRestorePanel/`), rendered inside `ReviewScreen` only
   * when the demo transparency feature flag is enabled AND the preview is
   * allowed.
   */
  exportRestorePanel: {
    heading: "Exportar e restaurar (demonstração)",
    disclaimer:
      "Este recurso existe para demonstrar o ciclo completo de exportação e restauração para fins de avaliação. Um produto final restringiria ou removeria esta superfície.",
    uploadOnlyNote:
      "A exportação HTTP está disponível apenas para o fluxo de envio de arquivo nesta demonstração.",
    exportButton: "Exportar",
    exportedPayloadHeading: "Representação divulgada exportada",
    restorableCountLabel: "itens restauráveis",
    expiresAtLabel: "Expira em:",
    treatmentLabel: "Tratamento:",
    strategyLabel: "Estratégia:",
    handleHeading: "Identificador de restauração",
    handleHiddenNotice: "O identificador é mantido apenas nesta tela, nunca salvo automaticamente.",
    copyHandleButton: "Copiar identificador",
    copyHandleSuccess: "Identificador copiado.",
    downloadHandleButton: "Baixar identificador (.txt)",
    importHandleLabel: "Importar identificador de um arquivo",
    simulateResponseHeading: "Simular resposta externa",
    simulateResponseHint:
      "Edite o texto abaixo como se fosse uma resposta recebida de fora do gateway, mantendo os pseudônimos que deseja restaurar.",
    restoreButton: "Restaurar localmente",
    restoredResultHeading: "Resultado da restauração",
    restoredCountLabel: "pseudônimos restaurados",
    unresolvedCountLabel: "tokens não reconhecidos por este identificador",
    unresolvedExplanation:
      "Tokens não reconhecidos têm formato de pseudônimo, mas não pertencem ao escopo deste identificador de restauração; eles permanecem inalterados no texto restaurado.",
    clearButton: "Limpar",
  },

  /**
   * T29 / issue #72: fail-closed presentation labels for the vault
   * explorer's `scope` field (`lib/vaultScopes.ts`). Same split as
   * `categories.labels` above -- keys are the frozen `PseudonymScope`
   * identifiers verbatim (never translated), only the value is
   * presentation prose. An unrecognized scope is reported as `unrecognized`
   * rather than prettified from its identifier, same posture as
   * `categories.unrecognized`.
   */
  vaultScopes: {
    unrecognized: "Escopo não reconhecido",
    technicalIdLabel: "Identificador técnico:",
    labels: {
      request: "Uma única requisição",
      document: "Um documento",
      session: "Uma sessão",
    } as Record<string, string>,
    explanations: {
      request: "Este pseudônimo só pode ser revertido dentro da mesma requisição que o criou.",
      document: "Este pseudônimo pode ser revertido em qualquer requisição sobre o mesmo documento.",
      session: "Este pseudônimo pode ser revertido em qualquer requisição da mesma sessão.",
    } as Record<string, string>,
  },

  /**
   * T29 / issue #72: the demo vault explorer panel
   * (`components/VaultExplorerPanel/`), rendered on the Review and Result
   * screens only when the demo vault explorer feature flag is enabled AND
   * the current preview carries a non-null `vault_explorer_token`.
   *
   * This panel is DELIBERATELY not merged with the T27 inspector
   * (`disclosureInspector` above): the inspector shows what changed in this
   * document's disclosed representation; this panel shows which reversible
   * local state -- the pseudonym -> original mapping -- stayed inside the
   * trust boundary for this decision. Two different questions, two
   * different data models, one conceptual link stated here in copy only.
   */
  vaultExplorerPanel: {
    heading: "Vault Explorer — Demonstração",
    subtitle: "Fronteira de confiança local",
    disclaimer:
      "Esta visão existe apenas para fins de demonstração e avaliação. Um produto final não exporia estes mapeamentos desta forma.",
    toggleLabel: "Ver o Vault Explorer (cofre local)",
    unavailableForDecision:
      "O Vault Explorer não está disponível para esta decisão (nenhuma referência foi emitida).",
    loadingLabel: "Carregando entradas do cofre local...",
    scopeLabel: "Escopo:",
    entryCountLabel: "entradas reversíveis",
    zeroEntriesMessage:
      "Esta decisão não deixou estado reversível local: o tratamento removeu ou generalizou os dados sensíveis em vez de pseudonimizá-los.",
    categoryLabel: "Categoria:",
    pseudonymLabel: "O que o serviço externo recebeu:",
    originalLabel: "O que permaneceu na fronteira local:",
    presentLabel: "Ainda mantido localmente",
    notPresentLabel: "Não está mais disponível localmente",
    showOriginalsToggle: "Mostrar valores originais",
    hideOriginalsToggle: "Ocultar valores originais",
    maskedValuePlaceholder: "••••••••",
    notAvailablePlaceholder: "—",
  },

  errors: {
    generic: "Não foi possível concluir a operação. Tente novamente.",
    upstreamUnreachable: "Não foi possível falar com o serviço no momento. Tente novamente em instantes.",
    validationFailed: "Os dados enviados não são válidos. Revise e tente novamente.",
    fileTooLarge: "O arquivo excede o limite aceito pelo serviço.",
    documentParsing: "Não foi possível processar este documento. Verifique o formato e tente novamente.",
    invalidAnalysisMode: "Esse tipo de análise não é aceito para o documento selecionado.",
    previewExpired: "Esta revisão não é mais válida. Faça uma nova revisão antes de enviar.",
    comparisonUnavailableForUpload: "A comparação ainda não está disponível para documentos estruturados.",
    demoTransparencyDisabled: "Este recurso de demonstração não está habilitado nesta implantação.",
    exportRefused: "Não foi possível gerar a exportação para este conteúdo.",
    restoreUnavailable: "A restauração local não está disponível nesta implantação no momento.",
    restoreHandleInvalid: "Este identificador de restauração não é válido.",
    restoreHandleExpired: "Este identificador de restauração expirou. Gere uma nova exportação.",
    demoVaultExplorerDisabled: "Este recurso de demonstração não está habilitado nesta implantação.",
    vaultExplorerReferenceInvalid:
      "Esta referência ao cofre local não é mais válida ou expirou. Faça uma nova revisão antes de continuar.",
  },

  sectionHeadings: {
    whatWasDetected: "O que foi detectado",
    whatStaysLocal: "O que permanece local",
    whatWasSent: "O que foi enviado",
    finalAnswer: "Resposta final",
    technicalDetails: "Detalhes técnicos",
    compareStrategies: "Comparar estratégias",
  },

  theme: {
    light: "Claro",
    dark: "Escuro",
    system: "Automático (sistema)",
    toggleLabel: "Tema",
  },

  /**
   * The switcher's own label (T21 fourth slice). The language NAMES
   * themselves ("Português", "English") live in `i18n/locales.ts`'s
   * `LOCALE_LABELS`, not here -- see that module for why.
   */
  language: {
    toggleLabel: "Idioma",
  },
} as const;

export { ptBR };

/**
 * Recursively widens a `const`-inferred literal type into the shape a
 * sibling locale can actually implement: every string literal (e.g.
 * `"Como funciona"`) becomes `string`, every (readonly) array becomes a
 * `readonly Widen<element>[]` (so a locale is free to have a different
 * number of, say, `howItWorks.steps`), and every other value keeps its own
 * type as-is (this table has no non-string primitives, but the type stays
 * correct if one is ever added). Object keys are never touched, which is
 * the whole point: a missing key, an extra key, or a value of the wrong
 * shape in a locale module is a compile error against `AppCopy`, while the
 * literal Portuguese words are not part of the contract.
 */
type Widen<T> = T extends string
  ? string
  : T extends readonly (infer U)[]
    ? readonly Widen<U>[]
    : T extends object
      ? { [K in keyof T]: Widen<T[K]> }
      : T;

export type AppCopy = Widen<typeof ptBR>;

/**
 * Picks the copy table for a given locale. `Locale` (from `web/i18n/locales`)
 * is a closed union, so this switch is exhaustive at compile time -- there
 * is no "unknown locale" branch to fall through here; an unparseable stored
 * value is rejected earlier, by `isSupportedLocale`, before it ever reaches
 * a `Locale`-typed value.
 */
export function resolveCopy(locale: Locale): AppCopy {
  switch (locale) {
    case "en":
      return en;
    case "pt-BR":
    default:
      return ptBR;
  }
}

/** The active locale's copy for callers with no locale context of their own. pt-BR is the product default. */
export const copy: AppCopy = ptBR;
