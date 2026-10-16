"""``@audited_step``: record a function as a pipeline step without touching its callers."""

import functools
import inspect
from typing import Any, Awaitable, Callable, Dict, Optional, ParamSpec, TypeVar, cast

from waypoint_etl import registry
from waypoint_etl.auditor import StepAuditor

P = ParamSpec("P")
R = TypeVar("R")

TAG = "__audited_step__"


def _input_values(
    auditor: StepAuditor,
    step: str,
    signature: inspect.Signature,
    rename: Dict[str, str],
    args: Any,
    kwargs: Any,
) -> Dict[str, object]:
    """Arguments of this call that the spec lists as inputs of ``step`` (by name)."""
    wanted = {name for s in auditor.spec.steps if s.name == step for name, _ in s.inputs}
    if not wanted:
        return {}
    try:
        bound = signature.bind(*args, **kwargs).arguments
    except TypeError:
        return {}
    named = {rename.get(param, param): value for param, value in bound.items()}
    return {k: v for k, v in named.items() if k in wanted}


def audited_step(
    name: str, inputs: Optional[Dict[str, str]] = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function or method as step ``name`` of the pipeline.

    Input counts come from the call's arguments, matched to the step's inputs in the pipeline spec
    by parameter name; ``inputs={"parameter": "input_name"}`` renames. With no active auditor (no
    ``waypoint_etl.init``) the decorated function behaves exactly like the original.
    """
    rename = inputs or {}

    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(fn)

        if inspect.iscoroutinefunction(fn):
            async_fn = cast(Callable[..., Awaitable[Any]], fn)

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                auditor = registry.get_active()
                if auditor is None:
                    return await async_fn(*args, **kwargs)
                index = auditor.begin(name)
                result = await async_fn(*args, **kwargs)
                auditor.finish(
                    name,
                    index,
                    _input_values(auditor, name, signature, rename, args, kwargs),
                    result,
                )
                return result

            setattr(async_wrapper, TAG, name)
            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auditor = registry.get_active()
            if auditor is None:
                return fn(*args, **kwargs)
            index = auditor.begin(name)
            result = fn(*args, **kwargs)
            auditor.finish(
                name,
                index,
                _input_values(auditor, name, signature, rename, args, kwargs),
                result,
            )
            return result

        setattr(wrapper, TAG, name)
        return cast(Callable[P, R], wrapper)

    return decorate


def wrap(
    obj: object, method_name: str, *, step: str, inputs: Optional[Dict[str, str]] = None
) -> None:
    """Audit ``obj.method_name`` as step ``step`` for code that cannot carry the decorator."""
    setattr(obj, method_name, audited_step(step, inputs)(getattr(obj, method_name)))
