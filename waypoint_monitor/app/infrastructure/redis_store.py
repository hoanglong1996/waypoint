import logging
import time
from typing import Any, List, Tuple

import redis

from app.domain.parsing import ROOT, pipeline_of_key
from app.infrastructure.store import StoreUnavailable

_BATCH = 200
# A died verdict normally expires with the run's heartbeat item; this is the fallback lifetime.
_DIED_FALLBACK_MS = 30 * 86_400_000
_WARN_EVERY_SECONDS = 60.0

log = logging.getLogger(__name__)


class RedisRecordStore:
    """Access to the pipelines' audit keys. Reads everything; its one write is `record_died`.

    Never deletes, and never modifies a key a pipeline wrote.
    """

    def __init__(self, url: str) -> None:
        # Short timeouts so an unreachable Redis fails fast; from_url does not connect.
        self.client = redis.Redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True
        )
        self._last_warning = float("-inf")

    def list_pipelines(self, env: str) -> List[str]:
        try:
            keys = (str(k) for k in self.client.scan_iter(match=f"{ROOT}:*:{env}:*", count=500))
            found = {name for name in (pipeline_of_key(env, k) for k in keys) if name}
            return sorted(found)
        except redis.RedisError as exc:
            raise StoreUnavailable(str(exc)) from exc

    def list_flows(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:flow")

    def list_records(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:step:*")

    def list_markers(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:running:*")

    def list_alive(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:alive")

    def list_died(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:died")

    def record_died(self, key: str, value: str, alive_key: str) -> bool:
        """`SET key value NX PX <remaining life of the heartbeat item>`; False on any failure."""
        try:
            remaining = self.client.pttl(alive_key)
            px = remaining if isinstance(remaining, int) and remaining > 0 else _DIED_FALLBACK_MS
            return bool(self.client.set(key, value, nx=True, px=px))
        except redis.RedisError as exc:
            now = time.monotonic()
            if now - self._last_warning >= _WARN_EVERY_SECONDS:
                self._last_warning = now
                log.warning("Could not record the died verdict for %s: %s", key, exc)
            return False

    def _scan(self, pattern: str) -> List[Tuple[str, str]]:
        try:
            keys = [str(k) for k in self.client.scan_iter(match=pattern, count=500)]
            out: List[Tuple[str, str]] = []
            for i in range(0, len(keys), _BATCH):
                batch = keys[i : i + _BATCH]
                values: List[Any] = list(self.client.mget(batch))  # type: ignore[arg-type]
                for key, value in zip(batch, values, strict=False):
                    if value is not None:
                        out.append((key, str(value)))
            return out
        except redis.RedisError as exc:
            raise StoreUnavailable(str(exc)) from exc

    def ping(self) -> None:
        try:
            self.client.ping()
        except redis.RedisError as exc:
            raise StoreUnavailable(str(exc)) from exc
