"""Where audit records go. A store only needs ``write``."""

import json
from typing import Dict, Protocol, Sequence, Tuple


class StepAuditStore(Protocol):
    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None: ...


class NoopStepAuditStore:
    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        return None

    def push_events(
        self, items: Sequence[Tuple[str, Sequence[str], int]], ttl_seconds: int
    ) -> None:
        return None

    def write_many(self, items: Sequence[Tuple[str, Dict[str, object]]], ttl_seconds: int) -> None:
        return None


class RedisStepAuditStore:
    """Stores each record as a JSON string that expires after ``ttl_seconds``."""

    def __init__(self, url: str) -> None:
        import redis  # needs the "redis" extra; imported here so the package imports without it

        # Short timeouts: an unreachable Redis must not stall the pipeline.
        # from_url does not connect; errors surface in write(), where the auditor catches them.
        self.client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.client.setex(key, ttl_seconds, json.dumps(record))

    def write_many(self, items: Sequence[Tuple[str, Dict[str, object]]], ttl_seconds: int) -> None:
        """``write`` for several records in one round trip (a non-transactional pipeline of ``SETEX``).

        A store that only has ``write`` simply has no ``write_many``: the map writer then writes one by one.
        """
        pipe = self.client.pipeline(transaction=False)
        for key, record in items:
            pipe.setex(key, ttl_seconds, json.dumps(record))
        pipe.execute()  # type: ignore[no-untyped-call]

    def push_events(
        self, items: Sequence[Tuple[str, Sequence[str], int]], ttl_seconds: int
    ) -> None:
        """Append event JSON to lists, keeping the newest ``cap`` of each and refreshing the TTL.

        ``items`` are ``(key, values, cap)`` triples, written in one transaction. A store that only
        has ``write`` simply has no ``push_events``: events are then skipped.
        """
        pipe = self.client.pipeline(transaction=True)
        for key, values, cap in items:
            pipe.rpush(key, *values)
            pipe.ltrim(key, -cap, -1)
            pipe.expire(key, ttl_seconds)
        pipe.execute()  # type: ignore[no-untyped-call]
