import unittest
from dataclasses import replace
from typing import Dict, List, Tuple
from unittest.mock import patch

import waypoint_etl
from waypoint_etl import PipelineSpec, StepSpec, registry

SPEC = PipelineSpec(name="demo", steps=(StepSpec("extract"),))
Entry = Tuple[str, Dict[str, object], int]


class FakeStore:
    def __init__(self) -> None:
        self.records: List[Entry] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))


class TestInit(unittest.TestCase):
    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_valid_init_registers_and_stores_the_flow(self) -> None:
        store = FakeStore()
        ok = waypoint_etl.init(
            pipeline=SPEC, redis_url=None, env="qa", ttl_days=2, run_id="R1", store=store
        )
        self.assertTrue(ok)
        self.assertIsNotNone(registry.get_active())
        key, record, ttl = store.records[0]
        self.assertEqual(key, "waypoint:demo:qa:R1:flow")
        self.assertEqual((record["v"], ttl), (waypoint_etl.FLOW_VERSION, 2 * 86400))

    def test_default_ttl_is_30_days(self) -> None:
        store = FakeStore()
        waypoint_etl.init(pipeline=SPEC, redis_url=None, env="qa", store=store)
        self.assertEqual(store.records[0][2], 30 * 86400)

    def test_invalid_spec_returns_false_and_stays_unaudited(self) -> None:
        with patch("builtins.print") as printed:
            ok = waypoint_etl.init(
                pipeline=replace(SPEC, name="Bad Name"), redis_url="redis://x", env="qa"
            )
        self.assertFalse(ok)
        self.assertIsNone(registry.get_active())
        self.assertIn("invalid pipeline spec", str(printed.call_args))

    def test_missing_redis_url_returns_false(self) -> None:
        for url in (None, ""):
            self.assertFalse(waypoint_etl.init(pipeline=SPEC, redis_url=url, env="qa"))
        self.assertIsNone(registry.get_active())

    def test_malformed_redis_url_returns_false_without_raising(self) -> None:
        self.assertFalse(waypoint_etl.init(pipeline=SPEC, redis_url="not-a-url", env="qa"))
        self.assertIsNone(registry.get_active())

    def test_second_init_replaces_the_first_with_a_warning(self) -> None:
        first, second = FakeStore(), FakeStore()
        waypoint_etl.init(pipeline=SPEC, redis_url=None, env="qa", run_id="A", store=first)
        with patch("builtins.print") as printed:
            waypoint_etl.init(pipeline=SPEC, redis_url=None, env="prod", run_id="B", store=second)
        self.assertIn("replacing", str(printed.call_args_list[0]))
        auditor = registry.get_active()
        assert auditor is not None
        self.assertEqual((auditor.run_id, auditor.env), ("B", "prod"))

    def test_error_settings_default_to_message_on_and_no_cleaner(self) -> None:
        waypoint_etl.init(pipeline=SPEC, redis_url=None, env="qa", store=FakeStore())
        auditor = registry.get_active()
        assert auditor is not None
        self.assertTrue(auditor.capture_error_message)
        self.assertIsNone(auditor.redact)

    def test_error_settings_are_passed_to_the_auditor(self) -> None:
        def clean(text: str) -> str:
            return text.upper()

        waypoint_etl.init(
            pipeline=SPEC,
            redis_url=None,
            env="qa",
            store=FakeStore(),
            capture_error_message=False,
            redact=clean,
        )
        auditor = registry.get_active()
        assert auditor is not None
        self.assertFalse(auditor.capture_error_message)
        self.assertIs(auditor.redact, clean)

    def test_a_redact_that_is_not_a_function_warns_and_is_ignored(self) -> None:
        with patch("builtins.print") as printed:
            ok = waypoint_etl.init(
                pipeline=SPEC, redis_url=None, env="qa", store=FakeStore(), redact="no"  # type: ignore[arg-type]
            )
        self.assertTrue(ok)
        self.assertIn("redact", str(printed.call_args_list))
        auditor = registry.get_active()
        assert auditor is not None
        self.assertIsNone(auditor.redact)

    def test_message_off_and_redact_reach_the_stored_failure(self) -> None:
        for kw, expected in (
            ({"capture_error_message": False}, None),
            ({"redact": lambda t: t.replace("jane@x.io", "<email>")}, "bad <email>"),
        ):
            store = FakeStore()
            waypoint_etl.init(
                pipeline=SPEC, redis_url=None, env="qa", run_id="R", store=store, **kw
            )

            @waypoint_etl.audited_step("extract")
            def fetch() -> None:
                raise ValueError("bad " + "jane" + "@x.io")

            with self.assertRaises(ValueError):
                fetch()
            (item,) = [r for k, r, _ in store.records if ":failed:" in k]
            error = item["error"]
            assert isinstance(error, dict)
            self.assertEqual(error.get("message"), expected)
            self.assertNotIn("jane@x.io", str(item))

    def test_keys_use_the_pipeline_name_and_env(self) -> None:
        store = FakeStore()
        waypoint_etl.init(pipeline=SPEC, redis_url=None, env="prod", run_id="R", store=store)

        @waypoint_etl.audited_step("extract")
        def fetch() -> int:
            return 1

        fetch()
        self.assertTrue(all(k.startswith("waypoint:demo:prod:R:") for k, _, _ in store.records))


if __name__ == "__main__":
    unittest.main()
