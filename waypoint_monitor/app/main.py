import argparse
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import build_router
from app.config import Settings, load_env_file
from app.infrastructure.redis_store import RedisRecordStore
from app.infrastructure.store import RecordStore

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(
    store: Optional[RecordStore] = None,
    settings: Optional[Settings] = None,
    clock: Optional[Callable[[], float]] = None,
    now: Optional[Callable[[], datetime]] = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if store is None:
        store = RedisRecordStore(settings.redis_url or "redis://localhost:6379/0")
    app = FastAPI(title="Waypoint Monitor", docs_url=None, redoc_url=None)
    app.include_router(build_router(store, settings, clock=clock, now=now))

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Waypoint Monitor web app")
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Load settings from .env.<config> (for example qa or prod); without it, .env is used if present",
    )
    args = parser.parse_args(argv)
    loaded = load_env_file(args.config)
    if args.config and loaded is None:
        parser.error(f".env.{args.config} not found in {Path.cwd()}")
    print(
        f"Loaded configuration from {loaded}"
        if loaded
        else "No .env file loaded; using environment"
    )
    settings = Settings.from_env()
    uvicorn.run(create_app(settings=settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
