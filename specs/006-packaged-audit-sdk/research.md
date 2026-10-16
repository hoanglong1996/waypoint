# Research: Packaged Pipeline Monitoring Product

## R1. How do steps get audited without rewriting application code?

**Decision**: a decorator, `@audited_step("step_name")`, placed on the use-case methods
(`ReadPartnerUseCase.execute`, etc.). It looks up the active auditor at call time.

**Rationale**: `EtlApplication.run_pipeline` then just calls `self.partner_uc.execute()`; the
`audit("...", fn, args, inputs={...})` wrappers disappear. Input counts come from the step's own
arguments, using the function's parameter names (`accounts`, `partners`, ...), so no `inputs` dict is
needed. Cost: one line per step method, in the file that already defines the step.

**Alternatives considered**:
- *Wrap from `main.py`* (`audit_steps(uc, "execute", "read_partners")`, monkeypatching/proxying): zero edits to use cases, but hidden behaviour, harder to read and to type-check. Offered as a documented fallback for code the adopter cannot edit (`step_audit.wrap(obj, "method", step="...")`), not the primary path.
- *Keep `auditor.run(...)`*: works but forces call-site edits, which the spec rules out.
- *Auto-instrument by scanning the spec* (import hooks): too magical.

## R2. Where does the pipeline identity/Redis config live?

**Decision**: `step_audit.init(pipeline=..., spec=..., redis_url=..., env=..., ttl_days=...)`, called
once from `main.py`. It validates the spec, builds the store and auditor and registers them in a
module-level registry. Before `init` (or if it fails) the decorator is a pass-through.

**Rationale**: matches the request (config in `main.py`) and the existing "no-op when unconfigured"
behaviour. A second `init` call replaces the first and logs a warning (deterministic, no mixed records).

**Alternatives**: constructor injection into `EtlApplication` (today's approach, touches application
code); a config file read by the library (a second config source next to `Config`).

## R3. Is the step list derivable from decorators?

**Decision**: no. `PipelineSpec` stays explicit and is passed to `init`. A package test
(`assert_spec_matches_steps`) is provided so adopters can check that decorated step names equal the
spec's step names, as callrail's test does today.

**Rationale**: hand-offs (which step feeds which) cannot be inferred from names alone, and the
dashboard needs them to draw edges.

## R4. Packaging and distribution

**Decision**: `packages/step_audit/` with a `src/` layout and `pyproject.toml` (distribution
`etl-step-audit`, extra `redis`). Callrail installs it as `-e ./packages/step_audit[redis]` in
development and as a path install inside its Docker build. Other pipelines install from a private
git URL pinned to a tag (`...git@bitbucket.org:...#subdirectory=integrations/callraill/packages/step_audit`).

**Rationale**: the monorepo has no root build system and integrations must stay self-contained, so no
private index is assumed. Git-tag pinning gives versioning (FR-002) without new infrastructure.

**Alternatives**: private PyPI/artifact registry (better long term, needs ops work, listed as follow-up);
copy-paste of the module (current state, the thing this feature removes).

## R5. Async and methods

**Decision**: the decorator detects coroutine functions and returns an async wrapper; methods work
because the wrapper uses `functools.wraps` and binds arguments via `inspect.signature` (skipping
`self`). Steps are assumed sequential within a run.

## R6. Concurrent runs and the run index

**Decision**: the registry holds one auditor per process; the run id is created at `init` (as today).
Concurrent runs of the same pipeline are separate processes with separate run ids. In-process
concurrency of steps is out of scope (documented).

## R7. Record format versioning

**Decision**: keep `FLOW_VERSION = 1`. The dashboard skips flows whose `v` is greater than it
supports and shows "unsupported version", instead of guessing.

## R8. Deployment bundle

**Decision**: `deploy/docker-compose.yml` with `redis` (volume, healthcheck), `monitor` (build from
`performance_monitoring_app/`, `REDIS_URL=redis://redis:6379/0`) and a `sample` service under a
compose profile that runs `examples/sample_pipeline.py` against the same Redis.

**Rationale**: gives the operator a one-command working stack (SC-005) and a smoke test of the whole chain.
