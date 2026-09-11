/**
 * One "what happens to this data" row. All interpretation comes from
 * `describeCategoryOutcome` (`lib/outcomes.ts`) -- this component never
 * looks at `category.outcome` itself, so it automatically inherits that
 * module's fail-closed behavior for an outcome it does not recognize.
 *
 * The category itself is presented through `describeCategory`
 * (`lib/categoryLabels.ts`) for the same reason: `category.category` is a
 * frozen policy identifier, not copy. It is still passed through untouched
 * -- it is simply not what the row is headlined with. When the identifier
 * is one this UI has no reviewed copy for, the row says so and shows the
 * raw identifier underneath as a technical detail rather than inventing a
 * friendly name for it.
 *
 * Issue #29's accessibility rule ("color is never the only indicator") is
 * why every row renders three independent signals: a non-color glyph
 * symbol, the tone color (via the CSS Module class), and the plain-text
 * label -- removing any one of the three still leaves the state legible
 * from the other two.
 */

import { useCopy } from "@/i18n/useLocale";
import { describeCategory } from "@/lib/categoryLabels";
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
  const copy = useCopy();
  const descriptor = describeCategoryOutcome(category, copy);
  const categoryDescriptor = describeCategory(category.category, copy);
  const glyphSymbol = GLYPH_SYMBOLS[descriptor.glyph] ?? "•";

  return (
    <li className={`${styles.row} ${TONE_CLASS[descriptor.tone]}`}>
      <div className={styles.headline}>
        <span className={styles.glyph} aria-hidden="true">
          {glyphSymbol}
        </span>
        <span className={styles.category}>{categoryDescriptor.label}</span>
        <span className={styles.label}>{descriptor.label}</span>
      </div>
      <span className={styles.boundary}>{descriptor.boundaryLabel}</span>
      <p className={styles.explanation}>{descriptor.explanation}</p>
      {!categoryDescriptor.known && (
        <p className={styles.technicalId}>
          {copy.categories.technicalIdLabel} <code>{categoryDescriptor.technicalId}</code>
        </p>
      )}
    </li>
  );
}
