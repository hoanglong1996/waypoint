import unittest

from waypoint_etl import keys


class TestKeys(unittest.TestCase):
    """Key layout: specs/007-rename-to-waypoint/contracts/redis-keys.md"""

    def test_prefix_is_waypoint(self) -> None:
        self.assertEqual(keys.ROOT, "waypoint")

    def test_key_formats(self) -> None:
        self.assertEqual(keys.flow_key("p", "qa", "R"), "waypoint:p:qa:R:flow")
        self.assertEqual(keys.step_key("p", "qa", "R", 3, "load"), "waypoint:p:qa:R:step:03-load")
        self.assertEqual(
            keys.marker_key("p", "qa", "R", 12, "load"), "waypoint:p:qa:R:running:12-load"
        )

    def test_alive_key_and_default_interval(self) -> None:
        # specs/009-run-liveness-heartbeat/contracts/redis-keys.md
        self.assertEqual(keys.alive_key("p", "qa", "R"), "waypoint:p:qa:R:alive")
        self.assertEqual(keys.HEARTBEAT_SECONDS, 15)

    def test_failed_key(self) -> None:
        # specs/011-step-failure-errors/contracts/redis-keys.md
        self.assertEqual(
            keys.failed_key("callrail", "prod", "20261017T020000Z", 2, "read_x"),
            "waypoint:callrail:prod:20261017T020000Z:failed:02-read_x",
        )
        self.assertEqual(
            keys.failed_key("p", "qa", "R", 12, "load"), "waypoint:p:qa:R:failed:12-load"
        )

    def test_events_key(self) -> None:
        # specs/012-duration-and-run-events/contracts/redis-keys.md
        self.assertEqual(
            keys.events_key("callrail", "prod", "20261017T020000Z", "warning"),
            "waypoint:callrail:prod:20261017T020000Z:events:warning",
        )
        for level in ("info", "warning", "error"):
            self.assertTrue(keys.events_key("p", "qa", "R", level).endswith(f":events:{level}"))
        with self.assertRaises(ValueError):
            keys.events_key("p", "qa", "R", "debug")

    def test_event_caps(self) -> None:
        self.assertEqual(keys.EVENT_CAPS, {"info": 500, "warning": 200, "error": 200})

    def test_flow_version_unchanged(self) -> None:
        self.assertEqual(keys.FLOW_VERSION, 1)


class TestMetricsKey(unittest.TestCase):
    def test_exact_key_and_padding(self) -> None:
        from waypoint_etl.keys import metrics_key

        self.assertEqual(
            metrics_key("demo", "qa", "20261017T020301Z", 7, "load"),
            "waypoint:demo:qa:20261017T020301Z:metrics:07-load",
        )
        self.assertTrue(metrics_key("demo", "qa", "r", 100, "x").endswith(":metrics:100-x"))


class TestMapKeys(unittest.TestCase):
    def test_map_and_item_keys(self) -> None:
        self.assertEqual(
            keys.map_key("callrail", "prod", "20261017T020301Z", "accounts"),
            "waypoint:callrail:prod:20261017T020301Z:map:accounts",
        )
        self.assertEqual(
            keys.item_key("callrail", "prod", "20261017T020301Z", "accounts", "acct-7"),
            "waypoint:callrail:prod:20261017T020301Z:item:accounts:acct-7",
        )

    def test_limits(self) -> None:
        self.assertEqual(
            (
                keys.MAP_VERSION,
                keys.MAP_DETAIL_LIMIT,
                keys.MAP_EXTRA_FAILED_LIMIT,
                keys.MAP_SLOWEST_KEPT,
                keys.MAX_ITEM_KEY,
                keys.MAX_INNER_STEPS,
                keys.ITEM_TRACE_BYTES,
                keys.COMPACT_MESSAGE,
                keys.MAP_FAILED_LISTED,
                keys.MAP_SLOWEST_LISTED,
                keys.EVICT_TTL_SECONDS,
            ),
            (1, 1000, 1000, 50, 64, 20, 2048, 200, 20, 5, 1),
        )


if __name__ == "__main__":
    unittest.main()
