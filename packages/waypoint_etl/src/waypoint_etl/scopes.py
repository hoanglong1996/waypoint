"""``map_step`` and ``item``: the two blocks an author adds around an existing loop.

    with waypoint_etl.map_step("accounts"):                  # the whole loop
        for account in accounts:
            with waypoint_etl.item(account.id):               # one pass: an id or index, never content
                fetch(account); transform(account); load(account)

Both work in plain code, in threads and in asyncio (``async with`` too). Neither suppresses an exception
and neither raises: with no ``init``, an unknown map step or a store that is down they do nothing.
Contract: specs/014-map-step-fan-out/contracts/library-api.md.
"""

import contextvars
from types import TracebackType
from typing import TYPE_CHECKING, Optional, Type

from waypoint_etl.events import current_step
from waypoint_etl.maps import ItemHandle, MapBlock, current_item, current_map

if TYPE_CHECKING:
    from waypoint_etl.auditor import StepAuditor


def _active() -> "Optional[StepAuditor]":
    from waypoint_etl import registry  # late: registry imports this module

    return registry.get_active()


class MapScope:
    """The block around a whole loop: the map step as an ordinary step, plus a tracker for its items."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._auditor: "Optional[StepAuditor]" = None
        self._block: Optional[MapBlock] = None
        self._map_token: "Optional[contextvars.Token[Optional[str]]]" = None
        self._step_token: "Optional[contextvars.Token[Optional[str]]]" = None

    def __enter__(self) -> "MapScope":
        try:
            auditor = _active()
            if auditor is not None:
                block = auditor.open_map(self._name)
                if block is not None:
                    self._auditor = auditor
                    self._block = block
                    self._map_token = current_map.set(self._name)
                    self._step_token = current_step.set(self._name)
        except Exception:
            pass
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        try:
            for var, token in ((current_step, self._step_token), (current_map, self._map_token)):
                if token is not None:
                    try:
                        var.reset(token)
                    except ValueError:
                        pass  # left from another context: nothing to restore
            if self._auditor is not None and self._block is not None:
                self._auditor.close_map(self._block, exc)
        except Exception:
            pass
        finally:
            self._block = None
            self._auditor = None
            self._map_token = None
            self._step_token = None

    async def __aenter__(self) -> "MapScope":
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.__exit__(exc_type, exc, tb)


class ItemScope:
    """One pass of the item flow for one key: what is recorded inside belongs to that item."""

    def __init__(self, key: object, map: Optional[str] = None) -> None:
        self._key = key
        self._map = map
        self._auditor: "Optional[StepAuditor]" = None
        self._handle: Optional[ItemHandle] = None
        self._token: "Optional[contextvars.Token[Optional[ItemHandle]]]" = None

    def __enter__(self) -> "ItemScope":
        try:
            auditor = _active()
            if auditor is None:
                return self
            block = auditor.resolve_block(self._map, current_map.get())
            if block is None:
                auditor._warn_map(
                    f"noscope:{self._map}",
                    "item() found no open map step"
                    + (f" named {self._map!r}" if self._map else "")
                    + "; nothing recorded for it",
                )
                return self
            self._auditor = auditor
            self._handle = auditor.start_item(block, self._key)
            self._token = current_item.set(self._handle)
        except Exception:
            pass
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        try:
            if self._token is not None:
                try:
                    current_item.reset(self._token)
                except ValueError:
                    pass
            if self._auditor is not None and self._handle is not None:
                self._auditor.end_item(self._handle, exc)
        except Exception:
            pass
        finally:
            self._handle = None
            self._auditor = None
            self._token = None

    async def __aenter__(self) -> "ItemScope":
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.__exit__(exc_type, exc, tb)
