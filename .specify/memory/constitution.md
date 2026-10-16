<!--
Sync Impact Report (temporary; remove before commit)
- Version change: (unfilled template) → 1.0.0
- Modified principles: none renamed (all five template slots filled for the first time)
- Added sections: Core Principles I–V, Technical Constraints, Development Workflow, Governance
- Removed sections: none
- Deferred items: none. Ratification date set to the adoption date of this first constitution.
-->
# CallRail ETL Pipeline Constitution

## Core Principles

### I. Layered Architecture
Code MUST be organised under `src/` as `domain/` (entities), `application/` (use cases),
`infrastructure/` (extract, transform, load, API clients) and `utils/` (config, logging, retry,
Sentry). Domain code MUST NOT import from infrastructure. Use cases orchestrate; infrastructure
performs external I/O. Rationale: keeps business logic testable without live APIs.

### II. Caller PII Protection (NON-NEGOTIABLE)
CallRail records contain caller names, phone numbers and transcriptions. This data MUST NOT reach
Sentry or logs. `send_default_pii` MUST stay `False`, the `EventScrubber` denylist MUST cover every
caller/recording field of any new entity, and frame locals MUST stay off by default
(`SENTRY_INCLUDE_LOCALS=false`). Secrets (API keys, OAuth tokens) MUST come from environment or
credential stores, never source control. Rationale: scrubbing matches keys only, so leaks via
`repr()` are otherwise undetectable.

### III. Type Safety and Code Quality
All code MUST be fully typed and pass `mypy` (strict), `ruff check` and `black` (line length 100,
Python 3.12) before merge. Rationale: a batch ETL job fails rarely and silently; static checks
catch schema drift early.

### IV. Test Coverage
New or changed behaviour in extract, transform, load and utils MUST have unit tests under `tests/`
mirroring the `src/` layout and runnable via `python -m unittest discover tests`. Tests MUST NOT
call live CallRail, Google Ads or Sentry services. Bug fixes MUST include a regression test.

### V. Resilient, Observable Execution
External API calls MUST use the shared retry utility. Unhandled failures MUST be reported to Sentry
(initialised at the top of `main()`) and MUST surface as a non-zero exit. With no `SENTRY_DSN` the
wiring MUST remain a no-op. Loads MUST be safe to re-run for the same date range without creating
duplicate data.

## Technical Constraints

- Runtime: Python 3.12+, shipped as a Docker image; runnable locally via `python main.py -c <env>`.
- Environment selection is by `-c` (`prod` / `qa`) with matching `.env.<env>` files; configuration
  MUST be read through `src/utils/config.py`.
- Integrations: CallRail API (extract), Google Ads ClickView (merge), warehouse load via
  `infrastructure/load`. Adding a new external source requires an entity in `domain/` and a
  dedicated extractor in `infrastructure/extract/`.
- New environment variables MUST be documented in `README.MD`.

## Development Workflow

- Work happens on feature/fix branches and is merged via pull request; reviewers MUST check
  compliance with this constitution.
- Before opening a PR, contributors MUST run `black .`, `ruff check .`, `mypy .` and the test suite.
- Changes touching PII-bearing entities MUST state in the PR how scrubbing was updated.
- Complexity beyond the layered structure MUST be justified in the PR description.

## Governance

This constitution supersedes other practices for this project. Amendments require a PR editing
`.specify/memory/constitution.md` with rationale and a version bump, approved by a maintainer, plus
a migration note if existing code becomes non-compliant. Versioning follows semantic versioning:
MAJOR for removed or redefined principles, MINOR for added principles or materially expanded
guidance, PATCH for clarifications. Compliance is reviewed on every PR; `README.MD` is the runtime
guidance reference.

**Version**: 1.0.0 | **Ratified**: 2026-10-15 | **Last Amended**: 2026-10-15
