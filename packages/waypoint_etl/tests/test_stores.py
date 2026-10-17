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

    def test_push_events_appends_trims_and_expires_in_one_transaction(self) -> None:
        with patch("redis.Redis.from_url") as from_url:
            client = MagicMock()
            from_url.return_value = client
            store = RedisStepAuditStore("redis://localhost:6379/0")
            store.push_events(
                [
                    ("waypoint:p:qa:R:events:info", ['{"n":1}', '{"n":2}'], 500),
                    ("waypoint:p:qa:R:events:error", ['{"n":3}'], 200),
                ],
                2592000,
            )
        client.pipeline.assert_called_once_with(transaction=True)
        pipe = client.pipeline.return_value
        self.assertEqual(
            [c.args for c in pipe.rpush.call_args_list],
            [
                ("waypoint:p:qa:R:events:info", '{"n":1}', '{"n":2}'),
                ("waypoint:p:qa:R:events:error", '{"n":3}'),
            ],
        )
        self.assertEqual(
            [c.args for c in pipe.ltrim.call_args_list],
            [("waypoint:p:qa:R:events:info", -500, -1), ("waypoint:p:qa:R:events:error", -200, -1)],
        )
        self.assertEqual(
            [c.args for c in pipe.expire.call_args_list],
            [("waypoint:p:qa:R:events:info", 2592000), ("waypoint:p:qa:R:events:error", 2592000)],
        )
        pipe.execute.assert_called_once_with()

    def test_the_noop_store_takes_events(self) -> None:
        from waypoint_etl.stores import NoopStepAuditStore

        self.assertIsNone(NoopStepAuditStore().push_events([("k", ["{}"], 5)], 60))

    def test_a_store_with_only_write_skips_events_with_one_warning(self) -> None:
        import io
        from contextlib import redirect_stdout

        from waypoint_etl import PipelineSpec, StepSpec, registry
        from waypoint_etl.auditor import StepAuditor

        class WriteOnly:
            def write(self, key: str, record: dict, ttl_seconds: int) -> None:  # type: ignore[type-arg]
                return None

        spec = PipelineSpec(name="demo", steps=(StepSpec("extract"),))
        registry.set_active(StepAuditor(WriteOnly(), spec, env="qa", ttl_seconds=1))  # type: ignore[arg-type]
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                for _ in range(3):
                    registry.log("one")
        finally:
            registry.clear()
        self.assertEqual(out.getvalue().count("cannot take events"), 1)


if __name__ == "__main__":
    unittest.main()
