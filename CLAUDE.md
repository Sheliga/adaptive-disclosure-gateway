# CLAUDE.md

Working reference for agent sessions on this repository. Keep it short and factual.

## Canonical treatment sequence

Direct → Static Sanitization → Reversible Pseudonymization → Task-aware → Policy-governed

| Code | Name |
| --- | --- |
| B0 | Direct |
| B1 | Static Sanitization |
| B2 | Reversible Pseudonymization |
| B3 | Task-aware |
| B4 | Policy-governed |

Treat this sequence as canonical in all reasoning, comparisons and prose. Comparisons are always adjacent: B0→B1, B1→B2, B2→B3, B3→B4.

## Frozen codes vs. semantic names

`b0`–`b4` are frozen experimental identifiers used for traceability across docs, cards, issues and telemetry. They must never change. Semantic names are for humans and appear in prose, module names, class names and doc headings.

Concretely:

- `Treatment` (`src/adaptive_disclosure_gateway/domain.py`) is the `StrEnum` whose members carry the semantic name (`DIRECT`, `STATIC_SANITIZATION`, `REVERSIBLE_PSEUDONYMIZATION`, `TASK_AWARE`, `POLICY_GOVERNED`) and whose values are the frozen codes (`"b0"`–`"b4"`).
- Module and class names for each treatment are semantic, not coded: `transformations/static_sanitization.py` / `StaticSanitizer` is the pattern to follow for B2–B4 (for example `reversible_pseudonymization.py` / `ReversiblePseudonymizer`).
- A treatment class exposes which treatment it implements through a `treatment` class attribute (for example `treatment = Treatment.STATIC_SANITIZATION`).
- OpenTelemetry spans/attributes are namespaced by the semantic name (for example `static_sanitization.sanitize`, `static_sanitization.span_count`) plus a `treatment` attribute carrying the frozen code as data (for example `"b1"`).
- In prose, never use a bare `B0`–`B4` where the semantic name fits. First occurrence in a document or active work item: `B2 — Reversible Pseudonymization`. Later occurrences may use the short code.
- **Active Trello cards and open GitHub Issues are living planning artifacts. Keep their treatment names, file paths and acceptance criteria synchronized with the current repository before implementation starts.** If an open Issue still says `b1.py` after the code moved to `static_sanitization.py`, or says only `B3` where the canonical name is available, update the active Issue/card first.
- **Closed GitHub Issues and merged PRs are historical artifacts. Do not rewrite their titles/descriptions merely to modernize naming.** Refer to them from current docs/cards using the current semantic name and note that the linked historical title may use the older wording.

## No-leak invariant

A sensitive value (an original, a pseudonym, a payload, detected/request text, secret/key
material) must never escape through a side channel -- not just be absent from the external
payload. This includes exception messages (and anything chained onto them via `__cause__`/
`__context__`), OTel span attributes, and log lines. Concretely:

- when raising, name the category, count, offset or type involved -- never interpolate the
  value itself into the message;
- when an underlying exception's own message might carry the value (e.g. a stdlib parser
  echoing its input), break the chain at the raise site (`raise ... from None`) rather than
  relying on the wrapping message being clean;
- when setting a span attribute, use metadata only (categories, counts, flags, timing), never
  the value, the payload or a pseudonym/original mapping.

This is enforced across `src/` by an AST-based test
(`tests/test_no_sensitive_value_in_raises.py`) that fails a build if a `raise` interpolates an
identifier that plausibly holds sensitive data (`value`, `text`, `payload`, `original`,
`pseudonym`, `secret`, `mapping`, including attribute accesses like `span.value`). If a
legitimate `raise` trips it, reword the message -- do not weaken the test. Telemetry itself is
separately pinned per-treatment in `tests/test_telemetry_privacy.py`.

## TDD

Development follows TDD. A test must be able to fail from a real defect in production code.

Never write sanity tests that only exercise test apparatus and cannot fail from a production bug. Prefer tests that pin security, behavioral, architectural or experimental invariants.

Before production code for a ticket:

1. write the smallest meaningful failing test;
2. confirm it fails for the expected reason;
3. implement the minimum change;
4. run focused tests;
5. run the complete suite;
6. run `ruff check .` and `ruff format --check .`.

## Workflow state

Use each system for one purpose:

- **Trello** — priority and workflow state;
- **GitHub Issue** — technical scope and acceptance criteria;
- **ADR / experimental-design.md** — frozen architectural and experimental decisions;
- **Pull Request** — candidate change under review;
- **master** — canonical implemented state.

Do not treat `code implemented`, `tests green`, `PR open`, `merged`, and `completed` as synonyms.

Expected flow:

`Próximas → Em andamento → Validação → Concluído`

- move a card to `Em andamento` when implementation actually starts;
- move it to `Validação` when the implementation is in an open PR ready for review;
- move it to `Concluído` only after the PR is merged and the Issue acceptance criteria are satisfied/closed;
- do not merge a PR or mark a Trello card complete without explicit user authorization;
- before starting a new ticket, read the current Trello card, linked GitHub Issue and relevant authoritative docs instead of relying on stale session context;
- when a review discovers a missing security/methodological invariant, update the active Issue/card acceptance criteria before calling the work complete.

## Authoritative documents

- [`docs/experimental-design.md`](docs/experimental-design.md) — treatment definitions, semantic-name mapping, pairwise comparisons, held-constant variables and metrics mapping. Authoritative for experimental design.
- [`docs/implementation-status.md`](docs/implementation-status.md) — what is merged, in validation and pending. Authoritative for engineering status.
