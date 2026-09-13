# ADR 0002 — Deferred restore through sealed, stateless restore handles

Status: accepted for T26 / Issue #67.

## Context

`POST /documents/preview` (and `adg preview`) already return the disclosed
representation of a document — the same `external_payload` shown on the
pre-disclosure review screen. What did not exist was a way to take that
representation **outside** the gateway (into another tool, another model, a
person's inbox) and, later, on request, restore the pseudonyms it contains
back to their originals, without the gateway retaining anything server-side
between the two calls.

Reconstruction as it existed before this ticket ran only inside one
`execute` call, over the provider's own response, using the vault and
governance context that call already had in hand
(`transformations/decision_application.reconstruct`). There was no route,
CLI command or service method that accepted arbitrary text plus some
after-the-fact authorization and returned the reconstruction — by design:
the pseudonym → original mapping must never be part of any response
(CLAUDE.md's no-leak invariant), so "export the mapping" was never on the
table. The feature this ADR designs is narrower and different in kind:
export **a specific, bounded set of entries actually disclosed in one
document**, sealed so only the deployment holding the key material can ever
open it, and restore **only** the pseudonyms an opened handle recognizes.

Constraints already fixed by the codebase and by the Issue:

- Ephemeral-by-default must remain the default (T25's stateless containers);
  retention is opt-in and explicit, never assumed.
- Pseudonyms are opaque 128-bit tokens (`vault/in_memory.py`); a restore
  mechanism must not become a second way to defeat that opacity.
- The advisor demo has no authentication; a restore endpoint reachable on a
  public URL is a re-identification oracle if it is not scope-bound.
- A guessable representation counts as a leak (CLAUDE.md); a public,
  reproducible digest of low-entropy content is not anonymizing it.
- `Vault`'s interface (`pseudonymize`/`reconstruct`, both scope-bound) must
  not grow an enumeration/export method — that would let anything holding a
  vault reference dump every mapping it has ever made, which is a much
  larger blast radius than one document's own already-disclosed entries.

## Decision

### D1 — Stateless sealed restore handle, no server-side retention

A restore handle is an AES-256-GCM envelope (`cryptography.hazmat.
primitives.ciphers.aead.AESGCM`) containing only the `(pseudonym ->
original)` entries that exist in one export's disclosed text, plus `v`
(schema version), `iat` and `exp`. Nothing is stored server-side; the handle
is the only place this data exists once the response leaves the process,
which is what lets it survive a restart or land on a different worker with
no shared state at all.

- **Key**: derived with HKDF-SHA256 from `ADG_RESTORE_HANDLE_SECRET` using a
  fixed domain-separation info label (`b"adg-restore-handle-v1"`), so the
  derived key is cryptographically independent of
  `ADG_PREVIEW_CONFIRMATION_SECRET` even if an operator (against documented
  guidance) reuses the same raw value for both mechanisms. The raw secret
  must be at least 32 bytes, exactly like the preview-confirmation secret's
  own requirement.
- **Nonce**: 96 bits, drawn fresh (`secrets.token_bytes(12)`) on every
  `issue()` call — never derived from content, so two exports of identical
  entries never produce the same handle.
- **AAD**: a fixed version/purpose label (`b"adg-restore-handle-v1"`),
  authenticating that a handle was sealed for this exact purpose and schema.
- **Wire form**: a version prefix plus base64url —
  `rh1.<b64url(nonce || ciphertext)>` — mirroring
  `application/preview_confirmation.py`'s `<version>.<claims>.<mac>` shape
  in spirit (a version tag first, so a schema change never gets
  reinterpreted under new rules) while carrying ciphertext instead of a MAC
  over recomputed claims, because a restore handle must carry data forward,
  not just prove a state was seen.
- **Plaintext padding**: the canonical JSON plaintext is padded (an ASCII
  `"pad"` field of `"0"` characters) to the next multiple of 256 bytes
  before encryption, so handle length reveals only which bucket the export
  fell into, not the exact byte length of any original value.

### D2 — No ephemeral-key mode

`PreviewConfirmationSigner.with_ephemeral_secret()` exists because a preview
confirmation only needs to outlive one browser round trip inside one
process. A restore handle is explicitly meant to outlive the issuing
process — that is the entire feature — so a per-process key would silently
defeat every handle the moment a worker restarts or a different worker
serves the restore call, with no error at issue time to say so. There is
deliberately no ephemeral mode here.

If `ADG_RESTORE_HANDLE_SECRET` is unset or blank, the service still
constructs and every other route (including `/health` and document
preview/execute) works normally. Only `export`/`restore` fail closed, at
call time, with `RestoreUnavailableError` — HTTP 503, CLI non-zero exit
naming the environment variable, never a value.

### D3 — Expiry and revocation

`exp` is authenticated inside the envelope (part of the AEAD-protected
plaintext, checked only after the tag verifies — an unauthenticated
timestamp must never be trusted). `ADG_RESTORE_HANDLE_TTL_SECONDS` defaults
to 86400 (24 hours) and must be a positive integer no greater than 604800
(7 days); an invalid value raises `RestoreHandleConfigurationError` at
construction — fail closed, no silent fallback to the default. The clock is
injectable (`RestoreHandleSealer(clock=...)`), mirroring
`PreviewConfirmationSigner`, so expiry is testable without sleeping.

Revocation is by secret rotation only: rotating
`ADG_RESTORE_HANDLE_SECRET` invalidates every previously issued handle at
once, because none of them decrypt under the new derived key. There is no
per-handle revocation list — that would require exactly the server-side
retention this design exists to avoid. Consequence: a compromised individual
handle cannot be revoked without also invalidating every other outstanding
handle; this is accepted given the TTL ceiling of 7 days bounds the exposure
window.

### D4 — Export

`DisclosureApplicationService.export(request)` accepts the identical
`DisclosureApplicationRequest` shape `preview`/`export` share (built via
`build_application_request` for text/file/example, or
`build_document_request` for a structured upload) and runs the same
decision phase `preview` runs — `decide_disclosure`, never the provider —
exactly once. A `BLOCK_REQUEST` outcome (or any decision that is not
`"allowed"`) raises `ExportRefusedError`: there is no disclosed
representation to export at all in that case.

The `(pseudonym -> original)` entries sealed into the handle are read
directly from `decision.result.transformations` — the same
`DisclosureResult` field `decision_application.reconstruct` already reads —
filtered to `DisclosureAction.PSEUDONYMIZE`. This needed **no new `Vault`
method and no change to the `Vault` interface**: every transformation the
decision itself produced already carries both the pseudonym it emitted
(`.transformed`) and the original it stands for (`.original`), so there is
nothing to look up. B0 — Direct and B1 — Static Sanitization never produce a
`PSEUDONYMIZE` transformation, so both always yield `restorable_count == 0`
with no treatment-specific branching in `export` itself; a REMOVE'd or
GENERALIZE'd category is equally absent from the entries for the same
reason, under any treatment.

### D5 — Restore

`DisclosureApplicationService.restore(text, restore_handle)` opens the
envelope (tampered / wrong or rotated key / truncated / malformed /
unsupported version / expired → fail closed, nothing reconstructed) and
replaces, in `text`, only the pseudonyms present in both `text` and the
handle's entries. Replacement reuses
`transformations.decision_application.replace_ordered` — the exact literal,
longest-first substring algorithm local reconstruction already uses — via a
small extraction from `reconstruct`'s own loop, rather than a second,
independently maintained implementation of the same algorithm.

Counting **unresolved** pseudonym-shaped tokens (present in the submitted
text but not in this handle — e.g. because they belong to a different
document's export) does need its own recognition step, since this call has
no `DisclosureResult`/vault to consult for "what counts as a pseudonym
here". `application/restore_handle._PSEUDONYM_TOKEN_PATTERN` recognizes the
already-public, fixed shape `vault/in_memory.py` emits
(`PSEUDO-<category>-<32 hex chars>` with an optional `-<suffix>`) purely to
count candidates; it never drives substitution, which is still restricted to
tokens the handle itself supplied. This is the mechanism the no-cross-scope
adversarial test relies on: a handle from document A applied to text
containing document B's pseudonyms leaves B's tokens untouched and reports
them only as a count.

The response carries `restored_text`, `restored_count` and
`unresolved_count` — never the mapping, and never an original for a
pseudonym absent from the submitted text.

### D6 — Surfaces

- **HTTP**: `POST /documents/export` (multipart, the same form fields/
  validation `/documents/preview` uses, reusing its request-building path
  verbatim; subject to the existing body-size middleware) and
  `POST /documents/restore` (JSON `{text, restore_handle}`, `extra="forbid"`
  pydantic model). `application/wire.py` gained `ExportResponse`/
  `RestoreResponse`; `CONTRACT_VERSION` was **not** bumped — both are
  additive response shapes, and this module's own convention is that adding
  a new response model is not an incompatible change to a shape a client
  already depends on.
- **CLI**: `adg export` (the same content-source flags `preview`/`execute`
  accept — `--text`/`--file`/`--example`; deliberately does **not** extend
  CLI ingestion to PDF/DOCX) and `adg restore`, which reads the handle from
  `--handle-file` and/or the text from `--text-file`, falling back to
  standard input for whichever one is omitted (never both — one stream
  cannot serve two independent inputs). The restore handle is never
  accepted as a plain argv value, so it never appears in a process listing
  or shell history the way an argument would.
- **No web proxy route and no UI in this PR.** T25 keeps the API
  internal-only behind the web proxy (see `docs/advisor-demo.md`), so
  export/restore are not reachable from the hosted demo URL until a later UI
  slice adds both a proxy route and a UI action. This is a scope decision,
  not a security one: nothing about the design prevents exposing it later.
- **Telemetry**: `restore_handle.issue` and `restore_handle.restore` spans,
  namespaced by the module's own semantic name exactly like every treatment
  module namespaces its own spans. Attributes are metadata only — entry
  counts, TTL, outcome kind (`ok`/`expired`/`invalid`) — never an entry's
  pseudonym or original, and never key material.

### D7 — Explicitly not in scope

UI, PDF/DOCX re-rendering of an export, authentication/accounts, any
persistence, any change to B2 — Reversible Pseudonymization, B3 — Task-aware
or B4 — Policy-governed semantics, the T10 runner, `post-pilot-v1`, corpora
or oracles.

## Alternatives rejected

- **Durable server-side vault, encrypted at rest.** Would need its own
  retention policy, key-at-rest management, and a story for what happens
  across a restart or a second worker picking up the restore request that
  never talked to the worker that issued the export. None of this is needed
  when the handle itself carries everything: rejected as unnecessary
  complexity and a strictly larger attack surface (a durable store of
  originals, rather than one handle a caller explicitly holds).
- **In-process TTL vault + a signed handle that only names an entry.** Loses
  everything on restart or when a different worker serves the restore call
  — exactly the ephemeral-container problem T25 exists to avoid — and still
  retains every original server-side for the TTL window, which the sealed
  envelope design avoids entirely by never retaining anything at all.
- **A hash/HMAC-only handle.** Cannot carry the originals forward at all — a
  digest is one-way by construction, so there would be nothing to restore.
  A content digest as a "proof of possession" was also considered and
  rejected outright: a public, reproducible digest of low-entropy content
  (a name, a CPF) is dictionary-reversible, which is exactly the guessable-
  representation leak CLAUDE.md already documents from this project's own
  history (a public SHA-256 of content stored in an audit record).

## Consequences

- Export/restore add no server-side state and no new persistence surface;
  the ephemeral-by-default posture and the stateless T25 containers are
  unaffected.
- A deployment that never configures `ADG_RESTORE_HANDLE_SECRET` gets every
  other feature unchanged and simply does not offer export/restore — this
  is the same fail-closed-but-otherwise-unaffected shape
  `ADG_PREVIEW_CONFIRMATION_SECRET`'s ephemeral fallback avoids for a
  different reason (there, a weaker mode exists for the deterministic
  provider; here, no weaker mode exists at all).
- Revocation is coarse (rotate the shared secret, invalidating everything),
  bounded by a hard 7-day TTL ceiling — a deliberate trade against the
  complexity of a per-handle revocation list, which would reintroduce
  server-side state.
- `cryptography` is now a **base** dependency (previously the codebase used
  only stdlib `hmac`/`hashlib` for `preview_confirmation.py`), because AEAD
  needs authenticated *encryption*, not just authentication — a keyed digest
  cannot carry data forward. Import isolation is pinned so this dependency
  is reachable from exactly one module (`application/restore_handle.py`).
- Until a UI slice adds a web-proxy route, export/restore exist only for
  API/CLI callers with direct access to the internal API — not reachable
  from the hosted advisor demo URL.
