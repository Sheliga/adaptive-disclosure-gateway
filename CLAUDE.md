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

The disclosure surface is the whole output boundary, not only the external payload. It
includes: the payload · the task/prompt · the provider request · exception messages and
anything chained onto them via `__cause__`/`__context__` · logs · telemetry · audit records ·
hashes and other derived identifiers. "The payload is clean" does not prove no disclosure
occurred -- the same pattern has recurred three times across the project's history, each a
separate real defect that escaped through a side channel after passing the main sanitization
path: `span.value` interpolated into an exception message; a sensitive value living only in
`request.task`; a public SHA-256 of the content stored in the audit record. Local behavioral
tests caught none of the three, because each checked the payload and nothing else.

A guessable representation counts as a leak. A public, reproducible digest of low-entropy
content is dictionary-reversible, so hashing content is not anonymizing it.

Therefore any change touching sensitive data needs, beyond its local behavioral tests, at
least one adversarial test that asks: if a sensitive value is placed here, is there any
alternative path by which it -- or a guessable representation of it -- can get out? AST-based
tests that apply repository-wide, such as the existing `raise` check in
`tests/test_no_sensitive_value_in_raises.py` and the import-isolation tests, are the most
durable form of this rule, because they also reach code that has not been written yet.

## TDD

Development follows TDD. A test must be able to fail from a real defect in production code.

Never write sanity tests that only exercise test apparatus and cannot fail from a production bug. Prefer tests that pin security, behavioral, architectural or experimental invariants.

Before production code for a ticket:

1. write the smallest meaningful failing test;
2. confirm it fails for the expected reason;
3. implement the minimum change;
4. run focused tests;
5. run the complete suite locally;
6. run `ruff check .` and `ruff format --check .` locally;
7. if `web/` changed, also run `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` from `web/` locally.

PRs targeting `develop` deliberately do not run GitHub Actions. This changes where validation runs, not whether validation is required. A PR description/review must state which relevant local gates were run and their result.

## Branching and CI

`develop` is the long-lived integration branch for work that belongs to the feature currently under development. `master` remains the canonical completed state.

Branch flow is mandatory unless the user explicitly directs otherwise:

`feature/* (or fix/*, chore/*) → develop → master`

Rules:

- start new implementation branches from the latest `develop`, not from `master`;
- every normal implementation PR targets `develop` while the current feature is incomplete;
- do not retarget an individual feature/slice PR to `master` merely because that slice is reviewable or locally green;
- merging a PR into `develop` means the slice is integrated into the in-progress feature; it does **not** mean the whole feature is canonical, released or complete;
- GitHub Actions CI does **not** run for PRs targeting `develop`; authors/reviewers must rely on the mandatory local gates in the TDD section for those intermediate PRs;
- when the full feature and its acceptance criteria are complete, open a single integration PR from `develop` to `master`;
- the `develop → master` PR is the CI boundary: the complete GitHub Actions suite must run and be green before merge;
- CI also runs on pushes to `master` as a post-integration safeguard;
- the final `develop → master` PR is merged only with the user's explicit authorization (see Merge authorization above for who executes it);
- after the final PR is merged, synchronize `develop` to the new `master` before starting the next feature so the next feature begins from the canonical state;
- direct feature PRs to `master` are not part of the normal workflow and require explicit user direction.

This CI strategy exists to reduce repeated GitHub Actions consumption while preserving one full remote validation at the feature integration boundary.

## Merge authorization

Repository Claude Code sessions must never execute PR merges. Merge approval belongs to the
user; merge execution is performed outside the repository Claude Code session.

- `.claude/settings.json` denies `Bash(gh pr merge:*)`. That blocks the `gh pr merge` command
  specifically from inside a Claude Code session -- it is not a claim that merging is
  impossible through every mechanism, only that this command is unavailable here.
- An agent may leave a PR ready, review it, comment on it, and report that it is ready to
  merge. It must not try to accomplish the merge through a different command or mechanism.
- `git merge` stays available: bringing a local branch up to date with `origin/develop` or
  `origin/master` is a different operation from merging a PR on GitHub, and is not restricted
  by this rule.

## Delegation

This section governs the main interactive session. It does not apply to a subagent already
executing a briefing: that subagent does the work itself and does not dispatch further
sub-subagents. A subagent that reads this file and starts spawning its own subagents has
misread it.

The main session orchestrates; it does not execute. It may run directly: read-only git
operations (`git status`, `git diff`, `git log`, `git show`, `git branch`, `git rev-parse`),
`git fetch --all --prune`, and any other inspection of branches, commits, diffs, working state
and history -- this, alongside reading Trello/GitHub state, is how it builds context. Deciding
scope, priority and sequence, writing the briefing a subagent will work from, and reviewing
what comes back also stay with the session itself.

Everything else that writes is dispatched to a subagent: editing any file; mutating git
operations such as `git add`, `git commit`, `git commit --amend`, `git rebase` and
`git cherry-pick`, creating or moving a branch as part of executing the task, and pushing;
creating/editing/closing a GitHub Issue or PR; creating/moving/editing a Trello card; and any
other mutating operation.

Model tiering for that dispatch: Haiku for mechanical, fully-specified work; Sonnet for
implementation inside a clear contract; Opus only for genuine architectural reasoning, which
is rare.

This trades away some output quality on purpose. The main session's accumulated context is
the scarce resource here, and this rule exists to stop that context being spent on execution
instead of orchestration.

Every briefing dispatched under this rule must open by telling the subagent to
`git fetch --all --prune` and verify its base is not behind before touching anything -- a local
branch is routinely behind its remote, and per Branching and CI above the base is normally
`develop`, not `master` -- and must restate three rules regardless of the task: TDD as defined
in this file, no `Co-Authored-By` trailer in commits, and never merge a PR.

## Workflow state

Use each system for one purpose:

- **Trello** — priority and workflow state;
- **GitHub Issue** — technical scope and acceptance criteria;
- **ADR / experimental-design.md** — frozen architectural and experimental decisions;
- **Pull Request to `develop`** — candidate slice/change under review for the current feature;
- **develop** — integrated but potentially incomplete state of the current feature;
- **Pull Request `develop → master`** — complete feature under final integration review and CI;
- **master** — canonical implemented state.

Do not treat `code implemented`, `tests green`, `PR open`, `merged into develop`, `merged into master`, and `completed` as synonyms.

Expected flow:

`Próximas → Em andamento → Validação → Concluído`

- move a card to `Em andamento` when implementation actually starts;
- move it to `Validação` when the relevant implementation is in an open PR ready for review;
- merging an intermediate PR into `develop` does not by itself move the overall feature to `Concluído`;
- move the feature to `Concluído` only after the final `develop → master` PR is merged and its acceptance criteria are satisfied/closed;
- a PR is merged, and a Trello card marked complete, only with explicit user authorization (see Merge authorization above);
- before starting a new ticket, read the current Trello card, linked GitHub Issue and relevant authoritative docs instead of relying on stale session context;
- when a review discovers a missing security/methodological invariant, update the active Issue/card acceptance criteria before calling the work complete.

## Authoritative documents

- [`docs/experimental-design.md`](docs/experimental-design.md) — treatment definitions, semantic-name mapping, pairwise comparisons, held-constant variables and metrics mapping. Authoritative for experimental design.
- [`docs/implementation-status.md`](docs/implementation-status.md) — what is merged, in validation and pending. Authoritative for engineering status.

## Local setup

Run the Python suite through the project venv, not the ambient interpreter:
`.venv/Scripts/python.exe -m pytest` on Windows, `.venv/bin/python -m pytest` on POSIX. A bare
`python -m pytest` fails collection with `ModuleNotFoundError: fastapi` -- that looks like a
regression and is not; it means the dependencies installed in the venv are not visible.

Enable the repository's git hooks once per clone: `git config core.hooksPath .githooks`.
