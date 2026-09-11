/**
 * Screen 1 -- "Boas-vindas / Como funciona" (`docs/advisor-demo.md`). The
 * three-step concept explanation already lives in `copy.ts`
 * (`copy.howItWorks.steps`) -- this component only lays it out, it never
 * invents its own wording.
 *
 * The doc's optional "Como funciona a pesquisa?" path (an explanatory
 * detour into B0-B4/the experiment design) is deliberately NOT built here:
 * this ticket's scope is steps 1-4 only, and that secondary path exists
 * precisely to hold the B0-B4 vocabulary the primary flow must never
 * surface. It is left for the "Comparar estratégias" / "Detalhes técnicos"
 * slice.
 */

import { useCopy } from "@/i18n/useLocale";

import styles from "./WelcomeScreen.module.css";

export function WelcomeScreen({ onStart }: { onStart: () => void }) {
  const copy = useCopy();
  return (
    <section aria-labelledby="welcome-heading" className={styles.section}>
      <h1 id="welcome-heading" className={styles.heading}>
        {copy.howItWorks.title}
      </h1>

      <ol className={styles.steps}>
        {copy.howItWorks.steps.map((step, index) => (
          <li key={step.title} className={styles.step}>
            <h2 className={styles.stepTitle}>
              {index + 1}. {step.title}
            </h2>
            <p>{step.description}</p>
          </li>
        ))}
      </ol>

      <div className={styles.actions}>
        <button type="button" className={styles.primaryButton} onClick={onStart}>
          {copy.howItWorks.ctaPrimary}
        </button>
      </div>
    </section>
  );
}
