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
    steps: [
      {
        title: "Análise local",
        description:
          "O documento é inspecionado antes de qualquer coisa sair do ambiente confiável.",
      },
      {
        title: "Divulgação controlada",
        description:
          "Apenas a representação permitida/transformada é enviada ao provedor externo.",
      },
      {
        title: "Reconstrução local",
        description: "Pseudônimos autorizados podem ser reconstruídos após a resposta do modelo.",
      },
    ],
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
    uploadDropHint: "Arraste um arquivo .txt ou .md aqui, ou escolha um arquivo.",
    uploadUnsupportedType: "Apenas arquivos .txt ou .md são aceitos.",
    uploadReadError: "Não foi possível ler o arquivo selecionado.",
    removeFile: "Remover arquivo",
    fileNameLabel: "Nome do arquivo",
    fileTypeLabel: "Tipo",
    fileSizeLabel: "Tamanho",
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
    showPayloadToggle: "Ver o payload exato que seria enviado",
    payloadByteCountLabel: "bytes",
    blockedHeading: "Solicitação bloqueada",
    blockedExplanation:
      "A política de divulgação bloqueou esta solicitação. Nada será enviado ao provedor externo.",
    confirmSend: "Confirmar e enviar",
    backToCompose: "Voltar e editar",
  },

  /** Screen 4 -- "Resultado". */
  result: {
    heading: "Resultado",
    pathHeading: "Caminho da informação",
    pathLocal: "Local",
    pathProvider: "Provedor externo",
    protectionsAppliedHeading: "Proteções aplicadas",
    blockedHeading: "Execução bloqueada",
    blockedExplanation:
      "A política de divulgação bloqueou esta execução. Nenhum conteúdo foi enviado ao provedor externo.",
    providerFailedHeading: "Falha ao consultar o provedor",
    providerFailedExplanation:
      "O provedor externo não respondeu com sucesso. Nenhuma resposta foi fabricada.",
    restart: "Testar novamente",
  },

  provider: {
    deterministicDemoLabel: "Provedor de demonstração determinístico — não é um modelo real.",
    /*
     * Shown when `GET /health` could not be reached or did not satisfy its
     * contract. Deliberately states only that the check failed -- it must
     * not read as "this is the demo provider" (a claim nothing verified)
     * nor be omitted (which reads as the verified real-provider case). See
     * lib/providerMode.ts.
     */
    modeUnverifiedLabel: "Modo do provedor não pôde ser verificado.",
  },

  processingStages: {
    readingFile: "Lendo o arquivo",
    detectingSensitiveData: "Detectando dados sensíveis",
    applyingDisclosurePolicy: "Aplicando política de divulgação",
    consultingModel: "Consultando o modelo",
    reconstructingAnswer: "Reconstruindo a resposta",
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

  errors: {
    generic: "Não foi possível concluir a operação. Tente novamente.",
    upstreamUnreachable: "Não foi possível falar com o serviço no momento. Tente novamente em instantes.",
    validationFailed: "Os dados enviados não são válidos. Revise e tente novamente.",
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
