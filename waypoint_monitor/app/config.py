import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _positive_float(name: str, default: float) -> float:
    value = _float(name, default)
    return value if value > 0 else default


def _positive_int(name: str, default: int) -> int:
    value = _int(name, default)
    return value if value >= 1 else default


def _envs() -> List[str]:
    raw = os.getenv("ENVIRONMENTS", "prod,qa")
    return [e.strip() for e in raw.split(",") if e.strip()] or ["prod", "qa"]


@dataclass(frozen=True)
class Settings:
    """Runtime settings, all from environment variables."""

    redis_url: str = ""
    environments: List[str] = field(default_factory=lambda: ["prod", "qa"])
    stale_hours: float = 26.0
    refresh_seconds: int = 5
    retry_seconds: int = 30
    port: int = 8080
    cache_seconds: int = 2
    stall_seconds: float = 900.0
    heartbeat_dead_seconds: float = 90.0
    slow_run_multiple: float = 2.0
    duration_window_runs: int = 30
    duration_min_runs: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            redis_url=os.getenv("REDIS_URL", ""),
            environments=_envs(),
            stale_hours=_float("STALE_HOURS", 26.0),
            refresh_seconds=_int("REFRESH_SECONDS", 5),
            retry_seconds=_int("RETRY_SECONDS", 30),
            port=_int("PORT", 8080),
            cache_seconds=_int("CACHE_SECONDS", 2),
            stall_seconds=_float("STALL_SECONDS", 900.0),
            heartbeat_dead_seconds=_float("HEARTBEAT_DEAD_SECONDS", 90.0),
            slow_run_multiple=_positive_float("SLOW_RUN_MULTIPLE", 2.0),
            duration_window_runs=_positive_int("DURATION_WINDOW_RUNS", 30),
            duration_min_runs=_positive_int("DURATION_MIN_RUNS", 5),
        )


def load_env_file(config: Optional[str], base_dir: Optional[Path] = None) -> Optional[Path]:
    """Load `.env.<config>` (or `.env` when no config is given) into the process environment.

    Variables already set in the real environment win over the file. Returns the file that was
    loaded, or None when it does not exist.
    """
    folder = base_dir or Path.cwd()
    path = folder / (f".env.{config}" if config else ".env")
    if not path.is_file():
        return None
    load_dotenv(path, override=False)
    return path
