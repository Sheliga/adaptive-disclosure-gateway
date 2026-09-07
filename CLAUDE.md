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
- Module and class names for each treatment are semantic, not coded: `transformations/static_sanitization.py` / `StaticSanitizer` is the pattern to follow for B2–B4 (e.g. `reversible_pseudonymization.py` / `ReversiblePseudonymizer`).
- A treatment class exposes which treatment it implements via a `treatment` class attribute (e.g. `treatment = Treatment.STATIC_SANITIZATION`).
- OpenTelemetry spans/attributes are namespaced by the semantic name (e.g. `static_sanitization.sanitize`, `static_sanitization.span_count`) plus a `treatment` attribute carrying the frozen code as data (e.g. `"b1"`). The frozen code lives in a value, never in an identifier a human has to decode.
- In prose, never use a bare `B0`–`B4` where the semantic name fits. First occurrence in a document: `B2 — Reversible Pseudonymization`. Later occurrences in the same document may use the short code.
- Do not rewrite the titles/descriptions of already-closed GitHub issues or PRs when they use the older bare-code phrasing — that would damage historical traceability.

## TDD

Development follows TDD. A test must be able to fail from a real defect in production code.

**Never write sanity tests** — tests that only exercise the test apparatus and cannot fail from a production bug: asserting an import succeeds, that an enum has N members, or that a constant equals the literal just written next to it with no invariant behind it. If a test cannot fail without also being wrong, do not write it.

## Authoritative documents

- [`docs/experimental-design.md`](docs/experimental-design.md) — the B0–B4 treatment definitions, the semantic-name mapping table, pairwise comparisons, what is held constant, and the metrics mapping. Authoritative for experimental design.
- [`docs/implementation-status.md`](docs/implementation-status.md) — what is implemented now, in validation, and pending. Authoritative for engineering status.
