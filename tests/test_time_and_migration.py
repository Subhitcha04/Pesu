"""A3 timezone boundaries, A12 migrations from a v0.1 data volume, F6 retention."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import auth, timeutil
from app.config import settings
from app.main import app

KID = "kavin-sample"

MIGRATION_001 = Path(__file__).resolve().parent.parent / "app" / "migrations" / "001_initial.sql"


def at(y, mo, d, h, mi):
    return lambda: datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_iso_is_utc_z_and_rejects_naive():
    assert timeutil.iso(datetime(2026, 11, 27, 18, 31, tzinfo=UTC)) == "2026-11-27T18:31:00Z"
    try:
        timeutil.iso(datetime(2026, 1, 1))
        raise AssertionError("naive datetime accepted")
    except ValueError:
        pass


def test_local_day_around_ist_midnight(client):
    # 18:29 UTC = 23:59 IST (same day); 18:31 UTC = 00:01 IST (next day).
    assert timeutil.local_day("2026-11-27T18:29:00Z") == "2026-11-27"
    assert timeutil.local_day("2026-11-27T18:31:00Z") == "2026-11-28"
    # 00:00-05:29 UTC still belongs to the same IST day as 05:30 UTC (v0.1 rolled over at 05:30 IST).
    assert timeutil.local_day("2026-11-28T00:10:00Z") == timeutil.local_day("2026-11-28T05:40:00Z") == "2026-11-28"


def test_today_counts_roll_over_at_ist_midnight(client):
    def try_at(clock):
        timeutil.set_clock(clock)
        client.post(
            "/api/attempts",
            data={"child_id": KID, "word_id": "kai", "pesu_verdict": "correct", "verdict": "correct", "decided_by": "pesu"},
        )

    try_at(at(2030, 1, 10, 18, 29))  # 23:59 IST on 10 Jan
    assert client.get(f"/api/children/{KID}/practice").json()["today"]["tries"] == 1
    timeutil.set_clock(at(2030, 1, 10, 18, 31))  # 00:01 IST on 11 Jan: a new day, nothing yet
    assert client.get(f"/api/children/{KID}/practice").json()["today"]["tries"] == 0
    try_at(at(2030, 1, 10, 18, 31))
    assert client.get(f"/api/children/{KID}/practice").json()["today"]["tries"] == 1
    timeutil.set_clock(at(2030, 1, 11, 4, 0))  # 09:30 IST 11 Jan, still the same IST day
    assert client.get(f"/api/children/{KID}/practice").json()["today"]["tries"] == 1


def test_day_start_utc():
    from datetime import date

    assert timeutil.day_start_utc(date(2026, 11, 28)) == "2026-11-27T18:30:00Z"


def test_migrates_v01_volume_in_place(tmp_path, monkeypatch):
    data = tmp_path / "old"
    data.mkdir()
    conn = sqlite3.connect(data / "pesu.db")
    conn.executescript(MIGRATION_001.read_text())
    conn.execute(
        "INSERT INTO children (id, name, age, word_ids, created_at) VALUES "
        "('c1','Old',5,'[\"kaakka\",\"kai\",\"kozhi\"]','2026-11-20T10:00:00.123456')"
    )
    conn.execute(
        "INSERT INTO attempts (id, child_id, session_id, ts, word_id, pesu_verdict, verdict, decided_by) "
        "VALUES ('a1','c1','s','2026-11-20T10:05:00.5','kaakka','error_t','correct','therapist')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("PESU_DATA_DIR", str(data))
    monkeypatch.setenv("PESU_DEMO", "0")
    settings.reload()
    auth.reset_secret_cache()
    with TestClient(app) as c:
        assert c.get("/api/health").json()["schema_version"] == 2
        c.post("/api/pin", json={"pin": "1234"})
        rows = c.get("/api/children/c1/attempts", params={"days": 90}).json()["attempts"]
        assert rows[0]["ts"] == "2026-11-20T10:05:00Z" and rows[0]["pesu_verdict"] == "error_t"
        # Second start is a no-op.
    with TestClient(app) as c:
        assert c.get("/api/health").json()["schema_version"] == 2
    settings.reload()


def test_retention_removes_old_audio_keeps_rows(therapist, monkeypatch):
    from app.db import db
    from app.main import apply_retention
    from tests.conftest import WEBM

    aid = therapist.post(
        "/api/attempts",
        data={"child_id": KID, "word_id": "kai", "pesu_verdict": "correct", "verdict": "correct", "decided_by": "pesu"},
        files={"audio": ("t.webm", WEBM, "audio/webm")},
    ).json()["id"]
    timeutil.set_clock(lambda: datetime.now(UTC) + timedelta(days=settings.retention_days + 1))
    assert apply_retention() >= 1
    with db() as conn:
        row = conn.execute("SELECT audio_path FROM attempts WHERE id = ?", (aid,)).fetchone()
    assert row["audio_path"] is None
    assert not list((settings.audio_dir / KID / "tries").glob(f"{aid}.*"))
