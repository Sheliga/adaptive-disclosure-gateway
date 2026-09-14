"use client";

/**
 * T29 / issue #72 -- the local demo Vault Explorer panel. Rendered from
 * `ReviewScreen` (below the T27 inspector) and `ResultScreen`, only when the
 * caller has already checked BOTH that the demo vault explorer feature flag
 * is enabled AND -- for the `token === null` unavailable case handled here
 * -- neither check is re-done by this component: it renders whatever
 * `token` it is given, exactly like `ExportRestorePanel` never re-checks
 * `demoTransparencyEnabled` itself.
 *
 * Collapsed by default: no request is made and no entry exists in the DOM
 * until the operator opens the panel. Each open triggers exactly one fetch
 * (`exploreVault`, via the gated vault explorer proxy route under
 * `app/api/demo/`); closing discards the fetched result from this
 * component's own `useState`
 * -- there is no separate "clear" action, closing IS the clear, and nothing
 * here is written to `localStorage`/`sessionStorage`/IndexedDB, cookies,
 * the URL, or any `console.*` call. Unmounting (leaving the screen,
 * restarting the flow, cancelling) discards it the same way, by React's own
 * unmount semantics -- there is nothing left to explicitly clear.
 *
 * Originals are MASKED by default with a fixed, non-length-revealing
 * placeholder (`copy.vaultExplorerPanel.maskedValuePlaceholder`) -- never a
 * truncated/partial form of the value itself (unlike
 * `ExportRestorePanel`'s `maskHandle`, which is fine to partially reveal an
 * OPAQUE handle but would be wrong here, where the masked value is exactly
 * the sensitive original). The one visible toggle reveals ALL originals at
 * once; there is no per-entry reveal, so there is no way to end up with a
 * mix of masked and revealed rows that could be screenshotted piecemeal to
 * defeat the point of masking.
 *
 * This panel does NOT merge its data model with the T27 inspector
 * (`DisclosureInspector`): the inspector answers "what changed in the
 * disclosed representation", this panel answers "which reversible local
 * state stayed inside the trust boundary for this decision" -- two
 * different questions over two different response shapes
 * (`DisclosureInspection` vs. `VaultExplorerResponse`), linked only in the
 * copy above, never in a shared type or shared fetch.
 */

import { useState } from "react";

import { useCopy } from "@/i18n/useLocale";
import { exploreVault, type DisplayError } from "@/lib/api";
import { describeCategory } from "@/lib/categoryLabels";
import type { VaultExplorerResponse } from "@/lib/contracts";
import { describeVaultScope } from "@/lib/vaultScopes";

import styles from "./VaultExplorerPanel.module.css";

export interface VaultExplorerPanelProps {
  /**
   * `PreviewResponse.vault_explorer_token`. `null` means the caller's
   * feature flag is on but this particular decision has no explorable
   * reference (blocked, ORGANIZATION scope, or unresolvable) -- rendered as
   * a short unavailable note instead of the interactive panel below.
   */
  token: string | null;
}

type FetchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "succeeded"; data: VaultExplorerResponse }
  | { status: "failed"; error: DisplayError };

export function VaultExplorerPanel({ token }: VaultExplorerPanelProps) {
  const copy = useCopy();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<FetchState>({ status: "idle" });
  const [showOriginals, setShowOriginals] = useState(false);

  if (token === null) {
    return (
      <section className={styles.panel} aria-labelledby="vault-explorer-heading">
        <h2 id="vault-explorer-heading">{copy.vaultExplorerPanel.heading}</h2>
        <p className={styles.subtitle}>{copy.vaultExplorerPanel.subtitle}</p>
        <p>{copy.vaultExplorerPanel.unavailableForDecision}</p>
      </section>
    );
  }

  async function handleOpen() {
    setOpen(true);
    setState({ status: "loading" });
    const result = await exploreVault(token as string, copy);
    if (result.ok) {
      setState({ status: "succeeded", data: result.data });
    } else {
      setState({ status: "failed", error: result.error });
    }
  }

  function handleClose() {
    // The whole "clear" step: dropping the local state IS what discards the
    // fetched data -- nothing was ever written anywhere else to also clear.
    setOpen(false);
    setState({ status: "idle" });
    setShowOriginals(false);
  }

  const data = state.status === "succeeded" ? state.data : null;

  return (
    <section className={styles.panel} aria-labelledby="vault-explorer-heading">
      <h2 id="vault-explorer-heading">{copy.vaultExplorerPanel.heading}</h2>
      <p className={styles.subtitle}>{copy.vaultExplorerPanel.subtitle}</p>
      <p className={styles.disclaimer}>{copy.vaultExplorerPanel.disclaimer}</p>

      <button type="button" onClick={open ? handleClose : handleOpen}>
        {copy.vaultExplorerPanel.toggleLabel}
      </button>

      {open && state.status === "loading" && <p>{copy.vaultExplorerPanel.loadingLabel}</p>}

      {open && state.status === "failed" && (
        <p role="alert" className={styles.error}>
          {state.error.message}
        </p>
      )}

      {open && data && (
        <div className={styles.results}>
          {data.scope === null ? (
            <p>{copy.vaultExplorerPanel.zeroEntriesMessage}</p>
          ) : (
            <>
              <p>
                {copy.vaultExplorerPanel.scopeLabel} {describeVaultScope(data.scope, copy).label}
              </p>
              <p>
                {data.entry_count} {copy.vaultExplorerPanel.entryCountLabel}
              </p>
            </>
          )}

          {data.entries.length > 0 && (
            <>
              <button type="button" onClick={() => setShowOriginals((previous) => !previous)}>
                {showOriginals
                  ? copy.vaultExplorerPanel.hideOriginalsToggle
                  : copy.vaultExplorerPanel.showOriginalsToggle}
              </button>
              <ul className={styles.list}>
                {data.entries.map((entry, index) => {
                  const categoryDescriptor = describeCategory(entry.category, copy);
                  const originalDisplay =
                    entry.original === null
                      ? copy.vaultExplorerPanel.notAvailablePlaceholder
                      : showOriginals
                        ? entry.original
                        : copy.vaultExplorerPanel.maskedValuePlaceholder;
                  return (
                    <li key={`${entry.category}-${index}`} className={styles.entry}>
                      <p>
                        {copy.vaultExplorerPanel.categoryLabel} {categoryDescriptor.label}
                      </p>
                      <p>
                        {copy.vaultExplorerPanel.pseudonymLabel} <code>{entry.pseudonym}</code>
                      </p>
                      <p>
                        {copy.vaultExplorerPanel.originalLabel} <code>{originalDisplay}</code>
                      </p>
                      <p>
                        {entry.present
                          ? copy.vaultExplorerPanel.presentLabel
                          : copy.vaultExplorerPanel.notPresentLabel}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
