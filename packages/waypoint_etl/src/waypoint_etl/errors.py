"""Turns an exception into the small, bounded, value-free ``error`` object of a failure item.

Contract: specs/011-step-failure-errors/contracts/redis-keys.md. The traceback is built from frames only
(file, line, function, source line): never variable values, and never the exception's own text unless
message capture is on. Nothing here raises.
"""

import os
import traceback
from typing import Callable, Dict, List, Optional

MAX_TYPE = 200
MAX_MESSAGE = 500
MAX_TRACEBACK_BYTES = 8192
MAX_CHAIN = 10
OMITTED = "... (earlier frames omitted)\n"

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep
_CAUSE = "\nThe above exception was the direct cause of the following exception:\n\n"
_CONTEXT = "\nDuring handling of the above exception, another exception occurred:\n\n"
_UNPRINTABLE = "<unprintable>"


def error_type(exc: BaseException) -> str:
    """Fully qualified class name (builtins and ``__main__`` without module), at most 200 chars."""
    cls = type(exc)
    name = (
        cls.__qualname__
        if cls.__module__ in ("builtins", "__main__")
        else (f"{cls.__module__}.{cls.__qualname__}")
    )
    return name[:MAX_TYPE]


def _message(
    exc: BaseException, capture: bool, redact: Optional[Callable[[str], str]]
) -> Optional[str]:
    """The cleaned message cut to 500 characters, or None (capture off, empty, or cleaning failed)."""
    if not capture:
        return None
    try:
        text = str(exc)
    except Exception:
        text = _UNPRINTABLE
    if redact is not None:
        try:
            cleaned = redact(text)
        except Exception:
            return None
        if not isinstance(cleaned, str):
            return None
        text = cleaned
    text = text[:MAX_MESSAGE]
    return text or None


def _frames(exc: BaseException) -> List[str]:
    try:
        summary = traceback.extract_tb(exc.__traceback__)
        own = [f for f in summary if not os.path.abspath(f.filename).startswith(_PACKAGE_DIR)]
        return list(traceback.format_list(own))
    except Exception:
        return []


def _chain(exc: BaseException) -> List[BaseException]:
    """The exception and its causes, innermost cause last in the list's reverse (oldest first)."""
    chain: List[BaseException] = []
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen and len(chain) < MAX_CHAIN:
        seen.add(id(current))
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    chain.reverse()
    return chain


def _pieces(exc: BaseException, capture: bool, redact: Optional[Callable[[str], str]]) -> List[str]:
    pieces: List[str] = []
    chain = _chain(exc)
    for position, item in enumerate(chain):
        if position:
            pieces.append(_CAUSE if item.__cause__ is chain[position - 1] else _CONTEXT)
        pieces.append("Traceback (most recent call last):\n")
        pieces.extend(_frames(item))
        message = _message(item, capture, redact)
        pieces.append(error_type(item) + (f": {message}" if message else "") + "\n")
    return pieces


def _fit(pieces: List[str]) -> str:
    """Join ``pieces``, dropping whole leading pieces until it fits in 8192 UTF-8 bytes."""
    sizes = [len(p.encode("utf-8")) for p in pieces]
    start = 0
    total = sum(sizes)
    omitted = False
    room = MAX_TRACEBACK_BYTES - len(OMITTED.encode("utf-8"))
    while total > MAX_TRACEBACK_BYTES and start < len(pieces) - 1:
        total -= sizes[start]
        start += 1
        omitted = True
        if total <= room:
            break
    text = "".join(pieces[start:])
    if omitted:
        text = OMITTED + text
    raw = text.encode("utf-8")
    if len(raw) > MAX_TRACEBACK_BYTES:
        raw = raw[-(MAX_TRACEBACK_BYTES - len(OMITTED.encode("utf-8"))) :]
        text = OMITTED + raw.decode("utf-8", errors="ignore")
    return text


def build_error(
    exc: BaseException,
    *,
    capture_message: bool = True,
    redact: Optional[Callable[[str], str]] = None,
) -> Dict[str, str]:
    """``{"type", "message"?, "traceback"}``. ``message`` is absent when it is not stored."""
    result: Dict[str, str] = {"type": error_type(exc)}
    message = _message(exc, capture_message, redact)
    if message is not None:
        result["message"] = message
    try:
        result["traceback"] = _fit(_pieces(exc, capture_message, redact))
    except Exception:
        result["traceback"] = result["type"] + "\n"
    return result
