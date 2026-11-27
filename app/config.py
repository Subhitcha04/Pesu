"""All runtime settings, read once from the environment. Every variable is optional.

Each one is documented in .env.example and in the README configuration table;
scripts/verify_readme.py fails if this list and the docs drift apart.
"""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


ROOT = Path(__file__).resolve().parent.parent

ENV_VARS = {
    # name: (default, description)
    "PESU_THERAPIST_PIN": ("1234", "Initial therapist PIN (4-6 digits). Once changed in the app, the stored PIN wins."),
    "PESU_NOISE_THRESHOLD": ("0.05", "Background RMS (0-1) above which Pesu pauses before listening."),
    "PESU_TZ": ("Asia/Kolkata", "Time zone used for 'today' and per-day charts."),
    "PESU_DEMO": ("0", "1 = seed the sample child and enable Judge Mode. docker-compose.yml sets 1."),
    "PESU_MIN_CONF": ("0.35", "Top recogniser confidence below this turns a definite verdict into 'unsure'. Uncalibrated."),
    "PESU_DATA_DIR": (str(ROOT / "data"), "Where the SQLite DB, audio and the token secret live."),
    "PESU_AUDIO_RETENTION_DAYS": ("90", "Child audio older than this is deleted at startup; verdict rows are kept."),
    "PESU_SECRET_FILE": ("", "Path of the token-signing secret. Default: <PESU_DATA_DIR>/secret.key (created on first run)."),
    "PESU_MAX_AUDIO_BYTES": ("2097152", "Largest accepted audio upload in bytes (default 2 MB)."),
}


def env(name: str) -> str:
    return os.getenv(name, ENV_VARS[name][0])


class Settings:
    """Re-readable so tests can change the environment and call reload()."""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self.default_pin = env("PESU_THERAPIST_PIN")
        self.noise_threshold = float(env("PESU_NOISE_THRESHOLD"))
        self.tz_name = env("PESU_TZ")
        self.tz = ZoneInfo(self.tz_name)
        self.demo = _flag("PESU_DEMO")
        self.min_conf = float(env("PESU_MIN_CONF"))
        self.data_dir = Path(env("PESU_DATA_DIR"))
        self.audio_dir = self.data_dir / "audio"
        self.db_path = self.data_dir / "pesu.db"
        self.retention_days = int(env("PESU_AUDIO_RETENTION_DAYS"))
        self.secret_file = Path(env("PESU_SECRET_FILE") or self.data_dir / "secret.key")
        self.max_audio_bytes = int(env("PESU_MAX_AUDIO_BYTES"))


settings = Settings()
VERSION = "0.2.0"
