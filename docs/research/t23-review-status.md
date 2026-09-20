# T23 review status

Last updated: 2026-09-11 (America/Sao_Paulo)

This document is retained as a historical review record for T23 / Issue #36. The review is no longer active.

## Final state

T23 is **complete**.

- PR #53 (`research/t23-freeze-protocol` → `develop`) was reviewed and merged.
- Final validated feature head: `b0fe17c4ae7109b2ea1d25d50218fe0957ebddb9`.
- Merge commit on `develop`: `15696a131d6bc16c19e810fa811767684b15ed51`.
- Canonical GitHub Actions validation: run #89, successful on the exact final head.
- Issue #36 was closed as completed.
- `docs/research/post-pilot-protocol-v1.md` (`protocol_id: post-pilot-v1`) is the frozen methodological baseline for the post-pilot path.

The older text in this file that described PR #53 as open/awaiting human merge was pre-merge review state and is superseded by this final record.

## Methodological result preserved

The final T23 freeze established, without tuning B3/B4 or the frozen HR evidence:

- ordinal/cumulative unnecessary-exposure analysis as the primary family;
- the historical binary unnecessary-disclosure metric preserved unchanged as secondary;
- explicit handling of scorable, blocked and unscorable `NOT_REQUIRED` spans (`N = S + B + U`);
- ordinal-safe macro summaries for max/median exposure;
- the five `hr-v2`/`hr-v3` contextual cells as the primary B3→B4 governance comparison;
- `hr-v1` pairwise as secondary/historical;
- FakeProvider limitations and the requirement for a real provider before authoritative utility/token/cost claims;
- paired descriptive analysis at the current scale;
- a development-vs-held-out/confirmatory freeze discipline for the next domain.

The known `hr_salary_analysis_003/salary` divergence remains visible and was not tuned away.

## Scientific order after T23

The frozen execution order became:

```text
T23 → T12 → Contracts domain extensions → T24 → next B0–B4 batch
```

T22 / real provider proceeds in parallel.

## Subsequent state

T12 / Issue #9 has since completed:

- PR #55 merged into `develop` as `776e683a49818db35021bb62315dfc1ed7fb00ab`;
- the exact T12 feature head was validated with real Docling 2.126.0 for PDF, DOCX and XLSX;
- normalized ingestion is now stable enough to leave the parser off the Contracts critical path.

The active scientific task is now Issue #56 — Contracts domain extensions — which must freeze the minimum domain-specific category/policy/generalization support before T24 builds/freezes Contracts v1 and its oracle.

See `docs/milestone-3-current-plan.md` for the current execution schedule and planning guardrails.