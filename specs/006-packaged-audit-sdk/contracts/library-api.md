# Contract: `step_audit` public API

Everything else in the package is private. Redis keys and values are specified in
`../../005-self-describing-pipeline-graph/contracts/redis-keys.md` and are not changed here.

## `step_audit.init`

```python
def init(
    *,
    pipeline: PipelineSpec,
    redis_url: str | None,
    env: str,
    ttl_days: int = 30,
    run_id: str | None = None,
    store: StepAuditStore | None = None,
) -> bool
```

- Call once from the entry point, before the first step.
- Returns `True` if auditing is active. Returns `False` (pipeline runs unaudited, a warning is
  printed, nothing raises) when the spec is invalid or `redis_url` is empty/invalid.
- Calling it again replaces the previous configuration and prints a warning.
- The pipeline name comes from `pipeline.name`; there is no separate name argument.
- `ttl_days` defaults to 30, matching feature 005. `store` replaces the Redis store (tests, other back ends).

## `step_audit.audited_step`

```python
@audited_step("read_partners")
def execute(self) -> list[Partner]: ...

@audited_step("read_instances")          # inputs default to the parameter names
def execute(self, partners: list[Partner]) -> list[Instance]: ...

@audited_step("merge_calls_clickview", inputs={"calls": "callrail_calls"})   # optional rename
```

- Works on functions, methods and `async def`; preserves name, signature, return value, exceptions.
- No active auditor → pure pass-through.
- Records only: step name, per-input item counts (None→None, collection→len, other→1), output count,
  timestamps. Never the values.
- `inputs`: optional mapping *parameter name → input name used in the spec*. Parameters not in the
  step's spec inputs are ignored.

## `step_audit.wrap` (fallback)

```python
step_audit.wrap(obj, "execute", step="read_partners")
```

Applies the same behaviour to code that cannot be edited. Documented, not recommended.

## Spec types

`PipelineSpec`, `StepSpec`, `GroupSpec` — as in feature 005, importable from `step_audit`.

## Test helper

`step_audit.testing.assert_spec_matches(spec, *objects)` fails if a decorated step name is missing
from the spec or a spec step has no decorated function among the given objects.

## Versioning

Semantic versions, git tags `step-audit-vX.Y.Z`. Record format changes bump `FLOW_VERSION`; the
dashboard shows "unsupported version" for flows newer than it knows.
