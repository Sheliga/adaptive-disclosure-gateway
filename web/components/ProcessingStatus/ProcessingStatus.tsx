/**
 * A named loading state -- issue #29 requires loading states to name the
 * current stage using the `copy.processingStages` strings, never a bare
 * spinner. `aria-live="polite"` plus `role="status"` means a screen reader
 * announces each stage as it appears, satisfying the "live regions for
 * async status" accessibility requirement.
 */

import styles from "./ProcessingStatus.module.css";

export function ProcessingStatus({ stages }: { stages: string[] }) {
  return (
    <div role="status" aria-live="polite" className={styles.status}>
      {stages.map((stage) => (
        <p key={stage} className={styles.stage}>
          {stage}
        </p>
      ))}
    </div>
  );
}
