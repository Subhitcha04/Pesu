"""Shared fixtures: every test gets a fresh data dir, demo data on, and the real lifespan startup."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import auth, timeutil
from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PESU_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PESU_DEMO", "1")
    monkeypatch.setenv("PESU_THERAPIST_PIN", "1234")
    settings.reload()
    auth.reset_secret_cache()
    with TestClient(app) as c:
        yield c
    timeutil.set_clock(None)
    settings.reload()
    auth.reset_secret_cache()


@pytest.fixture()
def therapist(client):
    r = client.post("/api/pin", json={"pin": "1234"})
    assert r.json()["ok"], r.text
    return client


# Smallest valid containers for upload tests (magic bytes are what matters).
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 3000
OGG = b"OggS" + b"\x00" * 3000
MP4 = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 3000
WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 3000
