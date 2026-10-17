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

    def test_flow_version_unchanged(self) -> None:
        self.assertEqual(keys.FLOW_VERSION, 1)


if __name__ == "__main__":
    unittest.main()
