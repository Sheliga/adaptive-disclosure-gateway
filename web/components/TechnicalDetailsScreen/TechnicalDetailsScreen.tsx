"use client";

/**
 * "Detalhes técnicos" -- T21 / issue #29's third slice. Reached from
 * Resultado via `copy.buttons.viewTechnicalDetails`; renders operational and
 * governance metadata already present on the SAME `ExecuteResponse`
 * Resultado holds -- no new request, no re-run of preview/execute/compare,
 * no scientific metric.
 *
 * Deliberately takes ONLY `execute: ExecuteResponse` as its data prop --
 * never `preview` -- so `PreviewResponse.external_payload` cannot reach this
 * screen even by accident: there is no prop to read it from. `final_answer`
 * and `summary`/categories (also on `ExecuteResponse`) are likewise never
 * read here; the primary answer and per-category outcome already have their
 * home on `ResultScreen`, and this screen would otherwise become a second,
 * uncontrolled place the same content could leak from.
 *
 * "Provedor" and "Reconstrução local" both handle their not-called/not-
 * attempted and failed states explicitly (never a crash, never a fabricated
 * value) -- a provider failure shows ONLY `failure_kind` (a safe category:
 * the raised exception's class name, see `audit.py`'s `ProviderStage`
 * docstring), never provider/exception text.
 *
 * `response_hash`/`reconstructed_hash` are HMAC-SHA256 digests keyed by a
 * process-local secret (see `audit.py`'s `_content_hash`), not a plain
 * public digest -- but CLAUDE.md's no-leak invariant still treats any
 * guessable/reproducible representation of content as a potential leak, so
 * both stay behind their own nested disclosure, kept OUT of the React tree
 * (not merely CSS-hidden) until explicitly opened -- the same pattern
 * `ComparisonScreen` uses for `external_payload`.
 *
 * `decoding_config` is arbitrary, provider-controlled structure. It is
 * rendered as bounded, non-recursive key/value rows (`formatDecodingValue`)
 * -- never by serializing the whole `ExecuteResponse` or recursing into
 * nested structures without a cap.
 */

import { Fragment, useState } from "react";

import type { ExecuteResponse, ProviderStage, ReconstructionStage } from "@/lib/contracts";
import { copy } from "@/lib/copy";

import styles from "./TechnicalDetailsScreen.module.css";

export interface TechnicalDetailsScreenProps {
  execute: ExecuteResponse;
  onBack: () => void;
}

function formatBoolean(value: boolean | null): string {
  if (value === null) {
    return copy.technicalDetails.notInformed;
  }
  return value ? copy.technicalDetails.yes : copy.technicalDetails.no;
}

function formatNullableString(value: string | null): string {
  return value ?? copy.technicalDetails.notInformed;
}

/**
 * Bounded, non-recursive rendering of one `decoding_config` value: a
 * primitive renders as itself; anything else is JSON-serialized and capped
 * at 200 characters. This is a controlled key/value row, never a dump of
 * the whole response.
 */
function formatDecodingValue(value: unknown): string {
  if (value === null || value === undefined) {
    return copy.technicalDetails.notInformed;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    const serialized = JSON.stringify(value);
    return serialized.length > 200 ? `${serialized.slice(0, 200)}…` : serialized;
  } catch {
    return copy.technicalDetails.notInformed;
  }
}

export function TechnicalDetailsScreen({ execute, onBack }: TechnicalDetailsScreenProps) {
  return (
    <section aria-labelledby="technical-details-heading" className={styles.section}>
      <h1 id="technical-details-heading" className={styles.heading}>
        {copy.sectionHeadings.technicalDetails}
      </h1>

      <div>
        <h2 className={styles.sectionHeading}>{copy.technicalDetails.executionHeading}</h2>
        <dl className={styles.rows}>
          <dt>{copy.technicalDetails.strategyLabel}</dt>
          <dd>
            <code>{execute.strategy}</code>
          </dd>
          <dt>{copy.technicalDetails.treatmentLabel}</dt>
          <dd>
            <code>{execute.treatment}</code>
          </dd>
        </dl>
        <p className={styles.explanation}>{copy.technicalDetails.strategyVsTreatmentExplanation}</p>
      </div>

      <div>
        <h2 className={styles.sectionHeading}>{copy.technicalDetails.governanceHeading}</h2>
        <dl className={styles.rows}>
          <dt>{copy.technicalDetails.domainLabel}</dt>
          <dd>{execute.governance.domain}</dd>
          <dt>{copy.technicalDetails.purposeLabel}</dt>
          <dd>{execute.governance.purpose}</dd>
          <dt>{copy.technicalDetails.policyVersionLabel}</dt>
          <dd>{execute.governance.policy_version}</dd>
          <dt>{copy.technicalDetails.providerClassLabel}</dt>
          <dd>{execute.governance.provider_class}</dd>
          <dt>{copy.technicalDetails.requesterRoleLabel}</dt>
          <dd>{formatNullableString(execute.governance.requester_role)}</dd>
          <dt>{copy.technicalDetails.requestedPseudonymScopeLabel}</dt>
          <dd>{execute.governance.requested_pseudonym_scope}</dd>
        </dl>
      </div>

      <ProviderSection provider={execute.provider} />

      <ReconstructionSection reconstruction={execute.reconstruction} />

      <div>
        <h2 className={styles.sectionHeading}>{copy.technicalDetails.timingHeading}</h2>
        <p className={styles.explanation}>{copy.technicalDetails.timingExplanation}</p>
        <p>
          {copy.technicalDetails.totalMsLabel}:{" "}
          <strong>
            {execute.total_ms} {copy.technicalDetails.millisecondsUnit}
          </strong>
        </p>
      </div>

      <button type="button" className={styles.backButton} onClick={onBack}>
        {copy.technicalDetails.backToResult}
      </button>
    </section>
  );
}

function ProviderSection({ provider }: { provider: ProviderStage }) {
  const [hashOpen, setHashOpen] = useState(false);

  if (!provider.called) {
    return (
      <div>
        <h2 className={styles.sectionHeading}>{copy.technicalDetails.providerHeading}</h2>
        <p>{copy.technicalDetails.providerNotCalledText}</p>
      </div>
    );
  }

  if (provider.failed) {
    return (
      <div>
        <h2 className={styles.sectionHeading}>{copy.technicalDetails.providerHeading}</h2>
        <div role="alert" className={styles.providerFailed}>
          <h3>{copy.technicalDetails.providerFailedHeading}</h3>
          <p>{copy.technicalDetails.providerFailedExplanation}</p>
          <dl className={styles.rows}>
            <dt>{copy.technicalDetails.providerFailureKindLabel}</dt>
            <dd>{formatNullableString(provider.failure_kind)}</dd>
          </dl>
        </div>
      </div>
    );
  }

  const decodingEntries = provider.decoding_config ? Object.entries(provider.decoding_config) : [];

  return (
    <div>
      <h2 className={styles.sectionHeading}>{copy.technicalDetails.providerHeading}</h2>
      <dl className={styles.rows}>
        <dt>{copy.technicalDetails.providerCalledLabel}</dt>
        <dd>{formatBoolean(provider.called)}</dd>
        <dt>{copy.technicalDetails.providerClassLabel}</dt>
        <dd>{formatNullableString(provider.provider_class)}</dd>
        <dt>{copy.technicalDetails.providerModelIdLabel}</dt>
        <dd>{formatNullableString(provider.model_id)}</dd>
        <dt>{copy.technicalDetails.providerModelSnapshotLabel}</dt>
        <dd>{formatNullableString(provider.model_snapshot)}</dd>
        <dt>{copy.technicalDetails.providerTransmittedBytesLabel}</dt>
        <dd>{provider.transmitted_bytes ?? copy.technicalDetails.notInformed}</dd>
      </dl>

      <div>
        <h3 className={styles.subHeading}>{copy.technicalDetails.providerDecodingConfigHeading}</h3>
        {decodingEntries.length === 0 ? (
          <p>{copy.technicalDetails.providerDecodingConfigEmpty}</p>
        ) : (
          <dl className={styles.rows}>
            {decodingEntries.map(([key, value]) => (
              <Fragment key={key}>
                <dt>
                  <code>{key}</code>
                </dt>
                <dd>{formatDecodingValue(value)}</dd>
              </Fragment>
            ))}
          </dl>
        )}
      </div>

      <details
        className={styles.hashDisclosure}
        open={hashOpen}
        onToggle={(event) => setHashOpen(event.currentTarget.open)}
      >
        <summary>{copy.technicalDetails.providerHashToggle}</summary>
        {hashOpen && (
          <p>
            {copy.technicalDetails.providerResponseHashLabel}:{" "}
            <code>{formatNullableString(provider.response_hash)}</code>
          </p>
        )}
      </details>
    </div>
  );
}

function ReconstructionSection({ reconstruction }: { reconstruction: ReconstructionStage }) {
  const [hashOpen, setHashOpen] = useState(false);

  return (
    <div>
      <h2 className={styles.sectionHeading}>{copy.technicalDetails.reconstructionHeading}</h2>
      <p className={styles.explanation}>{copy.technicalDetails.reconstructionExplanation}</p>
      <dl className={styles.rows}>
        <dt>{copy.technicalDetails.reconstructionAttemptedLabel}</dt>
        <dd>{formatBoolean(reconstruction.attempted)}</dd>
        <dt>{copy.technicalDetails.reconstructionChangedLabel}</dt>
        <dd>{formatBoolean(reconstruction.changed_from_provider_response)}</dd>
      </dl>
      {reconstruction.attempted && (
        <details
          className={styles.hashDisclosure}
          open={hashOpen}
          onToggle={(event) => setHashOpen(event.currentTarget.open)}
        >
          <summary>{copy.technicalDetails.reconstructionHashToggle}</summary>
          {hashOpen && (
            <p>
              {copy.technicalDetails.reconstructionHashLabel}:{" "}
              <code>{formatNullableString(reconstruction.reconstructed_hash)}</code>
            </p>
          )}
        </details>
      )}
    </div>
  );
}
