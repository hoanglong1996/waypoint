import json
import unittest
from unittest.mock import MagicMock, patch

from waypoint_etl.stores import RedisStepAuditStore


class TestRedisStepAuditStore(unittest.TestCase):
    def test_write_uses_setex_with_json(self) -> None:
        with patch("redis.Redis.from_url") as from_url:
            client = MagicMock()
            from_url.return_value = client
            store = RedisStepAuditStore("redis://localhost:6379/0")

            record = {"step": "read_x", "output": 10}
            store.write("callrail:audit:qa:R:01-read_x", record, 2592000)

        client.setex.assert_called_once()
        key, ttl, payload = client.setex.call_args.args
        self.assertEqual(key, "callrail:audit:qa:R:01-read_x")
        self.assertEqual(ttl, 2592000)
        self.assertEqual(json.loads(payload), record)

    def test_short_timeouts(self) -> None:
        with patch("redis.Redis.from_url") as from_url:
            RedisStepAuditStore("redis://localhost:6379/0")
        kwargs = from_url.call_args.kwargs
        self.assertEqual(kwargs["socket_connect_timeout"], 2)
        self.assertEqual(kwargs["socket_timeout"], 2)


if __name__ == "__main__":
    unittest.main()
