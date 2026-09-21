/**
 * Screen 1 -- "Boas-vindas / Como funciona" (`docs/advisor-demo.md`,
 * reorganized by T30 / issue #82).
 *
 * A first-time visitor (a prospective advisor) must understand, from this
 * screen alone: WHY the gateway exists, WHERE the trust boundary sits, and
 * WHAT the four possible transformations are -- all before ever seeing
 * B0-B4, vault or policy vocabulary. That vocabulary is confined to the
 * closed-by-default "Como funciona a pesquisa?" disclosure at the bottom,
 * which is the ONLY place on this screen it may appear (pinned by
 * `WelcomeScreen.test.tsx`'s "no B0-B4 vocabulary on the primary path"
 * suite).
 *
 * Reading order (all copy from `copy.ts`, never inlined):
 *  1. `howItWorks.title` (h1)
 *  2. `howItWorks.problem` -- the plain-language problem statement
 *  3. `howItWorks.trustBoundary` -- the visual local/external flow diagram
 *  4. `howItWorks.transformations` -- PRESERVE/REMOVE/PSEUDONYMIZE/GENERALIZE
 *     with tiny synthetic before->after examples
 *  5. the primary CTA
 *  6. the secondary, collapsed "Como funciona a pesquisa?" disclosure
 *
 * The trust-boundary diagram is semantic HTML/CSS (an ordered list), not an
 * image: each step carries its own group label as TEXT (`localGroupLabel`/
 * `externalGroupLabel`), so the boundary is legible from text content alone,
 * never from color/border styling only. `trustBoundary.diagramAlt` gives a
 * single-sentence text alternative for assistive technology that does not
 * enumerate list items one by one.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import type { AppCopy } from "@/lib/copy";

import styles from "./WelcomeScreen.module.css";

type TrustBoundaryStepKey = keyof AppCopy["howItWorks"]["trustBoundary"]["steps"];

const FLOW_STEPS: { key: TrustBoundaryStepKey; zone: "local" | "external" }[] = [
  { key: "originalDocument", zone: "local" },
  { key: "localGateway", zone: "local" },
  { key: "disclosedRepresentation", zone: "external" },
  { key: "externalLlm", zone: "external" },
  { key: "response", zone: "external" },
  { key: "localReconstruction", zone: "local" },
];

/** Canonical B0-B4 order (CLAUDE.md): never re-sorted or derived. */
const TREATMENT_ORDER = ["b0", "b1", "b2", "b3", "b4"] as const;

export function WelcomeScreen({ onStart }: { onStart: () => void }) {
  const copy = useCopy();
  const [researchOpen, setResearchOpen] = useState(false);
  const trustBoundary = copy.howItWorks.trustBoundary;
  const transformations = copy.howItWorks.transformations;

  return (
    <section aria-labelledby="welcome-heading" className={styles.section}>
      <h1 id="welcome-heading" className={styles.heading}>
        {copy.howItWorks.title}
      </h1>

      <div>
        <h2 className={styles.subheading}>{copy.howItWorks.problem.heading}</h2>
        <p>{copy.howItWorks.problem.statement}</p>
      </div>

      <div aria-labelledby="trust-boundary-heading">
        <h2 id="trust-boundary-heading" className={styles.subheading}>
          {trustBoundary.heading}
        </h2>
        <p className={styles.visuallyHidden}>{trustBoundary.diagramAlt}</p>
        <ol aria-labelledby="trust-boundary-heading" className={styles.flowDiagram}>
          {FLOW_STEPS.map((step, index) => (
            <li
              key={step.key}
              className={`${styles.flowStep} ${step.zone === "local" ? styles.zoneLocal : styles.zoneExternal}`}
            >
              <span className={styles.zoneLabel}>
                {step.zone === "local" ? trustBoundary.localGroupLabel : trustBoundary.externalGroupLabel}
              </span>
              <span className={styles.flowStepLabel}>
                {index + 1}. {trustBoundary.steps[step.key]}
              </span>
            </li>
          ))}
        </ol>
      </div>

      <div>
        <h2 className={styles.subheading}>{transformations.heading}</h2>
        <p>{transformations.intro}</p>
        <ul className={styles.transformationsList}>
          {[transformations.preserve, transformations.remove, transformations.pseudonymize, transformations.generalize].map(
            (kind) => (
              <li key={kind.label} className={styles.transformationCard}>
                <h3 className={styles.transformationLabel}>{kind.label}</h3>
                <p>{kind.description}</p>
                <p className={styles.example}>
                  <span className={styles.exampleBefore}>{kind.before}</span>
                  <span aria-hidden="true"> → </span>
                  <span className={styles.exampleAfter}>{kind.after}</span>
                </p>
              </li>
            ),
          )}
        </ul>
      </div>

      <div className={styles.actions}>
        <button type="button" className={styles.primaryButton} onClick={onStart}>
          {copy.howItWorks.ctaPrimary}
        </button>
      </div>

      <details
        className={styles.researchDisclosure}
        open={researchOpen}
        onToggle={(event) => setResearchOpen(event.currentTarget.open)}
      >
        <summary className={styles.researchToggle}>{copy.howItWorks.ctaSecondary}</summary>
        {researchOpen && (
          <div className={styles.researchContent}>
            <p>{copy.howItWorks.researchDisclosure.intro}</p>
            <ol className={styles.treatmentList}>
              {TREATMENT_ORDER.map((code) => (
                <li key={code} className={styles.treatmentCard}>
                  <h3>{copy.treatments[code].name}</h3>
                  <p>{copy.treatments[code].description}</p>
                </li>
              ))}
            </ol>
            <p>{copy.howItWorks.researchDisclosure.noChoiceNeeded}</p>
          </div>
        )}
      </details>
    </section>
  );
}
