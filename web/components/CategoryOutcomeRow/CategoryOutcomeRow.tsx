/**
 * One "what happens to this data" row. All interpretation comes from
 * `describeCategoryOutcome` (`lib/outcomes.ts`) -- this component never
 * looks at `category.outcome` itself, so it automatically inherits that
 * module's fail-closed behavior for an outcome it does not recognize.
 *
 * Issue #29's accessibility rule ("color is never the only indicator") is
 * why every row renders three independent signals: a non-color glyph
 * symbol, the tone color (via the CSS Module class), and the plain-text
 * label -- removing any one of the three still leaves the state legible
 * from the other two.
 */

import type { CategoryDisclosureSummary } from "@/lib/contracts";
import { describeCategoryOutcome, type DisclosureTone } from "@/lib/outcomes";

import styles from "./CategoryOutcomeRow.module.css";

const GLYPH_SYMBOLS: Record<string, string> = {
  trash: "\u{1F5D1}", // 🗑
  mask: "\u{1F3AD}", // 🎭
  blur: "▩", // ▩
  "check-shield": "\u{1F6E1}", // 🛡
  block: "⛔", // ⛔
  "alert-triangle": "⚠", // ⚠
};

const TONE_CLASS: Record<DisclosureTone, string> = {
  protected: styles.protected,
  sent: styles.sent,
  blocked: styles.blocked,
  unknown: styles.unknown,
};

export function CategoryOutcomeRow({ category }: { category: CategoryDisclosureSummary }) {
  const descriptor = describeCategoryOutcome(category);
  const glyphSymbol = GLYPH_SYMBOLS[descriptor.glyph] ?? "•";

  return (
    <li className={`${styles.row} ${TONE_CLASS[descriptor.tone]}`}>
      <div className={styles.headline}>
        <span className={styles.glyph} aria-hidden="true">
          {glyphSymbol}
        </span>
        <span className={styles.category}>{category.category}</span>
        <span className={styles.label}>{descriptor.label}</span>
      </div>
      <span className={styles.boundary}>{descriptor.boundaryLabel}</span>
      <p className={styles.explanation}>{descriptor.explanation}</p>
    </li>
  );
}
