import logging
import re
import time
from typing import Any, Dict, List, Tuple

import redis

from app.domain.parsing import EVENT_LEVELS, ROOT, event_list_key, pipeline_of_key
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

    def list_failures(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:failed:*")

    def list_metrics(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        return self._scan(f"{ROOT}:{pipeline}:{env}:*:metrics:*")

    def list_event_counts(self, env: str, pipeline: str) -> Dict[str, Dict[str, int]]:
        """Lengths of the warning and error lists of every run (`SCAN` for the names, one pipelined `LLEN`).

        A `ResponseError` (for example `NOPERM`) is not "store unavailable": the counts are then empty.
        """
        pattern = re.compile(
            rf"^{ROOT}:[^:]+:[^:]+:(?P<run>\d{{8}}T\d{{6}}Z):events:(?P<level>warning|error)$"
        )
        try:
            keys = [
                str(k)
                for k in self.client.scan_iter(
                    match=f"{ROOT}:{pipeline}:{env}:*:events:*", count=500
                )
            ]
            wanted = [(k, m["run"], m["level"]) for k in keys if (m := pattern.match(k))]
            if not wanted:
                return {}
            pipe = self.client.pipeline(transaction=False)
            for key, _run, _level in wanted:
                pipe.llen(key)
            lengths = pipe.execute()  # type: ignore[no-untyped-call]
        except redis.ResponseError as exc:
            self._warn_once(f"Could not read event counts: {exc}")
            return {}
        except redis.RedisError as exc:
            raise StoreUnavailable(str(exc)) from exc
        counts: Dict[str, Dict[str, int]] = {}
        for (_key, run, level), length in zip(wanted, lengths, strict=False):
            counts.setdefault(run, {"warning": 0, "error": 0})[level] = int(length or 0)
        return counts

    def read_events(self, env: str, pipeline: str, run_id: str) -> List[Tuple[str, List[str]]]:
        """`LRANGE 0 -1` of the three event lists of one run; a refused read gives nothing."""
        out: List[Tuple[str, List[str]]] = []
        try:
            for level in EVENT_LEVELS:
                key = event_list_key(pipeline, env, run_id, level)
                items = self.client.lrange(key, 0, -1)
                if items:
                    out.append((key, [str(i) for i in items]))  # type: ignore[union-attr]
        except redis.ResponseError as exc:
            self._warn_once(f"Could not read events: {exc}")
            return []
        except redis.RedisError as exc:
            raise StoreUnavailable(str(exc)) from exc
        return out

    def _warn_once(self, text: str) -> None:
        now = time.monotonic()
        if now - self._last_warning >= _WARN_EVERY_SECONDS:
            self._last_warning = now
            log.warning(text)

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
