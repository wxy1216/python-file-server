from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    api_token: str = os.getenv("API_TOKEN", "")
    storage_dir: Path = Path(
        os.getenv("FILE_STORAGE_DIR", str(BASE_DIR / "data" / "files"))
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://file_server:file_server@127.0.0.1:15432/file_server",
    )
    max_upload_size: int = _env_int("MAX_UPLOAD_SIZE", 100 * 1024 * 1024)
    file_chunk_size: int = max(
        1, _env_int("FILE_CHUNK_SIZE", 8 * 1024 * 1024)
    )


settings = Settings()
