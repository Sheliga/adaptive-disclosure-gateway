/**
 * A named loading state -- issue #29 requires loading states to say what is
 * happening, never a bare spinner. `aria-live="polite"` plus `role="status"`
 * announces it to screen readers ("live regions for async status").
 *
 * T32.2 / #102: one general `message` (plus an optional `detail`), never a
 * list of sequential sub-stages. The frontend has no backend progress
 * telemetry, so a stage list would imply observed progress it does not have.
 * Only static copy strings are ever passed here -- never request content --
 * so the live region cannot echo a sensitive value.
 */

import styles from "./ProcessingStatus.module.css";

export function ProcessingStatus({ message, detail }: { message: string; detail?: string }) {
  return (
    <div role="status" aria-live="polite" className={styles.status}>
      <p className={styles.stage}>{message}</p>
      {detail !== undefined && <p className={styles.stage}>{detail}</p>}
    </div>
  );
}
