import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings, load_env_file


class TestLoadEnvFile(unittest.TestCase):
    def test_loads_named_file(self) -> None:
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            (Path(d) / ".env.qa").write_text("REDIS_URL=redis://example:1/2\nPORT=9000\n")
            loaded = load_env_file("qa", Path(d))
            settings = Settings.from_env()
        self.assertEqual(loaded, Path(d) / ".env.qa")
        self.assertEqual(settings.redis_url, "redis://example:1/2")
        self.assertEqual(settings.port, 9000)

    def test_real_environment_wins_over_file(self) -> None:
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"PORT": "7000"}, clear=True),
        ):
            (Path(d) / ".env.qa").write_text("PORT=9000\n")
            load_env_file("qa", Path(d))
            self.assertEqual(Settings.from_env().port, 7000)

    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_env_file("qa", Path(d)))
            self.assertIsNone(load_env_file(None, Path(d)))

    def test_no_config_uses_plain_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            (Path(d) / ".env").write_text("STALE_HOURS=5\n")
            self.assertEqual(load_env_file(None, Path(d)), Path(d) / ".env")
            self.assertEqual(Settings.from_env().stale_hours, 5.0)

    def test_heartbeat_dead_seconds(self) -> None:
        for env, expected in (({}, 90.0), ({"HEARTBEAT_DEAD_SECONDS": "30"}, 30.0)):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                self.assertEqual(Settings.from_env().heartbeat_dead_seconds, expected)
        with patch.dict(os.environ, {"HEARTBEAT_DEAD_SECONDS": "soon"}, clear=True):
            self.assertEqual(Settings.from_env().heartbeat_dead_seconds, 90.0)

    def test_defaults_without_any_settings(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s = Settings.from_env()
        self.assertEqual((s.redis_url, s.environments, s.refresh_seconds), ("", ["prod", "qa"], 5))
        self.assertEqual((s.cache_seconds, s.stall_seconds), (2, 900.0))

    def test_stall_seconds_override(self) -> None:
        with patch.dict(os.environ, {"STALL_SECONDS": "30", "REFRESH_SECONDS": "9"}, clear=True):
            s = Settings.from_env()
        self.assertEqual((s.stall_seconds, s.refresh_seconds), (30.0, 9))


if __name__ == "__main__":
    unittest.main()
