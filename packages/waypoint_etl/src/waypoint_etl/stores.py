"""Where audit records go. A store only needs ``write``."""

import json
from typing import Dict, Protocol


class StepAuditStore(Protocol):
    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None: ...


class NoopStepAuditStore:
    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
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
