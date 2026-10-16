import fnmatch
import unittest
from typing import Tuple
from unittest.mock import MagicMock, patch

import redis

from app.infrastructure.redis_store import RedisRecordStore
from app.infrastructure.store import StoreUnavailable

PATH = "app.infrastructure.redis_store.redis.Redis.from_url"


class TestRedisRecordStore(unittest.TestCase):
    def _store(self) -> Tuple[RedisRecordStore, MagicMock, MagicMock]:
        with patch(PATH) as from_url:
            client = MagicMock()
            from_url.return_value = client
            store = RedisRecordStore("redis://localhost:6379/0")
        return store, client, from_url

    def test_short_timeouts(self) -> None:
        _, _, from_url = self._store()
        kwargs = from_url.call_args.kwargs
        self.assertEqual(kwargs["socket_connect_timeout"], 2)
        self.assertEqual(kwargs["socket_timeout"], 2)

    def test_scan_pattern_and_mget_batches(self) -> None:
        store, client, _ = self._store()
        keys = [f"waypoint:demo:prod:R:step:{i:02d}-s" for i in range(450)]
        client.scan_iter.return_value = iter(keys)
        client.mget.side_effect = lambda batch: [f"v{k}" if k != keys[1] else None for k in batch]

        out = store.list_records("prod", "demo")

        client.scan_iter.assert_called_once_with(match="waypoint:demo:prod:*:step:*", count=500)
        self.assertEqual(client.mget.call_count, 3)  # 200 + 200 + 50
        self.assertEqual(len(out), 449)  # one missing value skipped

    def test_flow_and_marker_patterns_skip_expired(self) -> None:
        store, client, _ = self._store()
        client.scan_iter.return_value = iter(
            ["waypoint:demo:prod:R:flow", "waypoint:demo:prod:S:flow"]
        )
        client.mget.return_value = ["{}", None]
        self.assertEqual(store.list_flows("prod", "demo"), [("waypoint:demo:prod:R:flow", "{}")])
        client.scan_iter.assert_called_once_with(match="waypoint:demo:prod:*:flow", count=500)
        client.scan_iter.return_value = iter([])
        store.list_markers("prod", "demo")
        client.scan_iter.assert_called_with(match="waypoint:demo:prod:*:running:*", count=500)

    def test_pipelines_discovered_from_any_key_kind_and_deduplicated(self) -> None:
        store, client, _ = self._store()
        run = "20261015T020000Z"
        client.scan_iter.return_value = iter(
            [
                f"waypoint:callrail:prod:{run}:flow",
                f"waypoint:callrail:prod:{run}:step:01-a",
                f"waypoint:orphan:prod:{run}:running:01-a",  # no flow key: still discovered
                f"waypoint:other:qa:{run}:flow",  # another env
                f"callrail:audit:prod:{run}:01-a",  # old layout
            ]
        )
        self.assertEqual(store.list_pipelines("prod"), ["callrail", "orphan"])
        client.scan_iter.assert_called_once_with(match="waypoint:*:prod:*", count=500)
        client.mget.assert_not_called()

    def test_redis_error_becomes_store_unavailable(self) -> None:
        store, client, _ = self._store()
        client.scan_iter.side_effect = redis.ConnectionError("nope")
        for call in (
            lambda: store.list_records("prod", "demo"),
            lambda: store.list_flows("prod", "demo"),
            lambda: store.list_markers("prod", "demo"),
            lambda: store.list_pipelines("prod"),
        ):
            with self.assertRaises(StoreUnavailable):
                call()
        client.ping.side_effect = redis.ConnectionError("nope")
        with self.assertRaises(StoreUnavailable):
            store.ping()

    def test_only_read_commands_used(self) -> None:
        store, client, _ = self._store()
        for call in (
            lambda: store.list_records("prod", "demo"),
            lambda: store.list_flows("prod", "demo"),
            lambda: store.list_markers("prod", "demo"),
            lambda: store.list_pipelines("prod"),
        ):
            client.scan_iter.return_value = iter([])
            call()
        store.ping()
        used = {c[0] for c in client.method_calls}
        self.assertLessEqual(used, {"scan_iter", "mget", "ping"})

    def test_alive_and_died_scan_patterns(self) -> None:
        store, client, _ = self._store()
        client.scan_iter.return_value = iter(["waypoint:demo:prod:R:alive"])
        client.mget.return_value = ["{}"]
        self.assertEqual(store.list_alive("prod", "demo"), [("waypoint:demo:prod:R:alive", "{}")])
        client.scan_iter.assert_called_once_with(match="waypoint:demo:prod:*:alive", count=500)
        client.scan_iter.return_value = iter([])
        store.list_died("prod", "demo")
        client.scan_iter.assert_called_with(match="waypoint:demo:prod:*:died", count=500)

    def test_alive_and_died_errors_become_store_unavailable(self) -> None:
        store, client, _ = self._store()
        client.scan_iter.side_effect = redis.ConnectionError("nope")
        for method in (store.list_alive, store.list_died):
            with self.assertRaises(StoreUnavailable):
                method("prod", "demo")

    def test_record_died_sets_once_with_the_alive_items_remaining_ttl(self) -> None:
        store, client, _ = self._store()
        client.pttl.return_value = 86_400_000
        client.set.return_value = True
        self.assertTrue(store.record_died("k:died", "{v}", "k:alive"))
        client.pttl.assert_called_once_with("k:alive")
        client.set.assert_called_once_with("k:died", "{v}", nx=True, px=86_400_000)
        used = {c[0] for c in client.method_calls}
        self.assertEqual(used, {"pttl", "set"})  # no delete, no other write

    def test_record_died_falls_back_to_30_days_without_a_ttl(self) -> None:
        for pttl in (-1, -2, None):
            with self.subTest(pttl=pttl):
                store, client, _ = self._store()
                client.pttl.return_value = pttl
                client.set.return_value = True
                self.assertTrue(store.record_died("k:died", "{v}", "k:alive"))
                self.assertEqual(client.set.call_args.kwargs["px"], 30 * 86_400_000)

    def test_record_died_returns_false_when_it_already_exists(self) -> None:
        store, client, _ = self._store()
        client.pttl.return_value = 1000
        client.set.return_value = None  # NX refused: another monitor stored it first
        self.assertFalse(store.record_died("k:died", "{v}", "k:alive"))

    def test_record_died_never_raises_and_warns(self) -> None:
        for error in (
            redis.ConnectionError("down"),
            redis.ResponseError("NOPERM this user has no permissions to run the 'set' command"),
        ):
            with self.subTest(error=type(error).__name__):
                store, client, _ = self._store()
                client.pttl.return_value = 1000
                client.set.side_effect = error
                with self.assertLogs("app.infrastructure.redis_store", "WARNING"):
                    self.assertFalse(store.record_died("k:died", "{v}", "k:alive"))
        store, client, _ = self._store()
        client.pttl.side_effect = redis.TimeoutError("slow")
        with self.assertLogs("app.infrastructure.redis_store", "WARNING"):
            self.assertFalse(store.record_died("k:died", "{v}", "k:alive"))

    def test_record_died_warns_at_most_once_a_minute(self) -> None:
        store, client, _ = self._store()
        client.pttl.return_value = 1000
        client.set.side_effect = redis.ConnectionError("down")
        with self.assertLogs("app.infrastructure.redis_store", "WARNING") as logs:
            for _ in range(5):
                store.record_died("k:died", "{v}", "k:alive")
        self.assertEqual(len(logs.records), 1)

    def test_a_monitor_without_this_feature_never_matches_the_new_keys(self) -> None:
        """Those monitors scan only these patterns, so alive and died items are invisible to them."""
        old_patterns = (
            "waypoint:demo:prod:*:flow",
            "waypoint:demo:prod:*:step:*",
            "waypoint:demo:prod:*:running:*",
        )
        new_keys = ("waypoint:demo:prod:R:alive", "waypoint:demo:prod:R:died")
        for key in new_keys:
            for pattern in old_patterns:
                with self.subTest(key=key, pattern=pattern):
                    self.assertFalse(fnmatch.fnmatchcase(key, pattern))

    def test_the_scan_patterns_in_use_are_the_ones_an_old_monitor_has(self) -> None:
        store, client, _ = self._store()
        client.scan_iter.return_value = iter([])
        store.list_flows("prod", "demo")
        store.list_records("prod", "demo")
        store.list_markers("prod", "demo")
        patterns = [c.kwargs["match"] for c in client.scan_iter.call_args_list]
        self.assertEqual(
            patterns,
            [
                "waypoint:demo:prod:*:flow",
                "waypoint:demo:prod:*:step:*",
                "waypoint:demo:prod:*:running:*",
            ],
        )


if __name__ == "__main__":
    unittest.main()
