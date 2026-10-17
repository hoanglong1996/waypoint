import json
import unittest
from typing import Dict, Optional

from waypoint_etl.errors import MAX_MESSAGE, MAX_TRACEBACK_BYTES, OMITTED, _fit, build_error

TOKEN = "SEC" + "RET"  # built at run time so the marker is data, not part of any source line


def raise_value_error(text: str = "boom") -> None:
    secret = "S3CR3T-LOCAL"  # noqa: F841  (a local that must never reach the report)
    raise ValueError(text)


def capture(exc_fn: object = raise_value_error, **kwargs: object) -> Dict[str, str]:
    try:
        exc_fn()  # type: ignore[operator]
    except Exception as exc:
        return build_error(exc, **kwargs)  # type: ignore[arg-type]
    raise AssertionError("did not raise")


class TestBuildError(unittest.TestCase):
    def test_type_message_traceback(self) -> None:
        err = capture()
        self.assertEqual(err["type"], "ValueError")
        self.assertEqual(err["message"], "boom")
        self.assertIn("raise_value_error", err["traceback"])
        self.assertIn("test_errors.py", err["traceback"])
        self.assertIn("ValueError: boom", err["traceback"])

    def test_module_qualified_type(self) -> None:
        err = capture(lambda: json.loads("{"))
        self.assertEqual(err["type"], "json.decoder.JSONDecodeError")

    def test_type_capped(self) -> None:
        cls = type("N" * 400, (Exception,), {})

        def boom() -> None:
            raise cls("x")

        self.assertEqual(len(capture(boom)["type"]), 200)

    def test_message_capped(self) -> None:
        err = capture(lambda: raise_value_error("m" * 5000))
        self.assertEqual(len(err["message"]), MAX_MESSAGE)
        self.assertEqual(MAX_MESSAGE, 500)

    def test_no_variable_values(self) -> None:
        err = capture()
        self.assertNotIn("S3CR3T-LOCAL", json.dumps(err).replace('secret = "S3CR3T-LOCAL"', ""))

    def test_unprintable_message(self) -> None:
        class Bad(Exception):
            def __str__(self) -> str:
                raise RuntimeError("no")

        def boom() -> None:
            raise Bad()

        err = capture(boom)
        self.assertEqual(err["message"], "<unprintable>")

    def test_sdk_frames_dropped(self) -> None:
        err = capture()
        self.assertNotIn("waypoint_etl/errors.py", err["traceback"])

    def test_empty_message_is_absent(self) -> None:
        def boom() -> None:
            raise KeyError()

        self.assertNotIn("message", capture(boom))

    def test_traceback_capped_keeps_last_pieces(self) -> None:
        pieces = [f'  File "f{i}.py", line {i}, in fn{i}\n    call_{i}()\n' for i in range(400)]
        pieces.append("RuntimeError: innermost\n")
        text = _fit(pieces)
        self.assertLessEqual(len(text.encode("utf-8")), MAX_TRACEBACK_BYTES)
        self.assertTrue(text.startswith(OMITTED))
        self.assertTrue(text.rstrip().endswith("RuntimeError: innermost"))
        self.assertIn("f399.py", text)
        self.assertNotIn("f0.py", text)

    def test_short_traceback_is_untouched(self) -> None:
        self.assertEqual(_fit(["a\n", "b\n"]), "a\nb\n")

    def test_one_piece_larger_than_cap_keeps_its_tail(self) -> None:
        text = _fit(["x" * 20000 + "TAIL\n"])
        self.assertLessEqual(len(text.encode("utf-8")), MAX_TRACEBACK_BYTES)
        self.assertTrue(text.startswith(OMITTED) and text.endswith("TAIL\n"))

    def test_single_huge_frame_is_hard_cut(self) -> None:
        err = capture(lambda: raise_value_error("é" * 400))
        self.assertLessEqual(len(err["traceback"].encode("utf-8")), MAX_TRACEBACK_BYTES)

    def test_chained_causes_are_separate_blocks(self) -> None:
        def boom() -> None:
            try:
                raise KeyError("inner")
            except KeyError as inner:
                raise ValueError("outer") from inner

        err = capture(boom)
        text = err["traceback"]
        self.assertEqual(err["message"], "outer")
        self.assertIn("KeyError: 'inner'", text)
        self.assertIn("The above exception was the direct cause", text)
        self.assertLess(text.index("KeyError"), text.index("ValueError: outer"))

    def test_implicit_context_block(self) -> None:
        def boom() -> None:
            try:
                raise KeyError("first")
            except KeyError:
                raise ValueError("second")  # noqa: B904

        self.assertIn("During handling of the above exception", capture(boom)["traceback"])

    def test_message_off_removes_message_everywhere(self) -> None:
        def boom() -> None:
            try:
                raise KeyError(TOKEN + "-inner")
            except KeyError as inner:
                raise ValueError(TOKEN + "-outer") from inner

        err = capture(boom, capture_message=False)
        self.assertNotIn("message", err)
        self.assertNotIn("SECRET", json.dumps(err))
        self.assertIn("ValueError\n", err["traceback"])

    def test_redact_applies_to_message_and_chain(self) -> None:
        def boom() -> None:
            try:
                raise KeyError(TOKEN + "-inner")
            except KeyError as inner:
                raise ValueError(TOKEN + "-outer") from inner

        err = capture(boom, redact=lambda t: t.replace("SECRET", "***"))
        self.assertEqual(err["message"], "***-outer")
        self.assertNotIn("SECRET", json.dumps(err))

    def test_redact_expansion_stays_capped(self) -> None:
        err = capture(redact=lambda t: t * 1000)
        self.assertEqual(len(err["message"]), 500)

    def test_failing_or_bad_redact_drops_message(self) -> None:
        def raises(_: str) -> str:
            raise RuntimeError("x")

        bad: Optional[object] = lambda t: 5  # noqa: E731
        for fn in (raises, bad):
            err = capture(redact=fn)
            self.assertNotIn("message", err)
            self.assertNotIn("boom", json.dumps(err))

    def test_secret_local_not_in_report(self) -> None:
        err = capture()
        self.assertNotIn("S3CR3T-LOCAL", err["traceback"].replace('secret = "S3CR3T-LOCAL"', ""))


if __name__ == "__main__":
    unittest.main()
