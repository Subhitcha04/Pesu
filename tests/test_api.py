"""API tests (F15) with a temp data dir. IDs refer to the defects/features in the README."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.config import settings
from tests.conftest import MP4, OGG, WAV, WEBM

KID = "kavin-sample"


def add_child(c, name="Meena", age=3):
    r = c.post("/api/children", json={"name": name, "age": age})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def save_try(c, child, verdict="correct", decided_by="pesu", audio=None, session=""):
    files = {"audio": ("t.webm", audio, "audio/webm")} if audio else None
    data = {
        "child_id": child,
        "word_id": "kaakka",
        "pesu_verdict": verdict if verdict != "unscored" else "unscored",
        "verdict": verdict,
        "decided_by": decided_by,
        "session_id": session,
    }
    return c.post("/api/attempts", data=data, files=files)


def test_health_reports_schema(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["schema_version"] == 2 and h["demo"] is True


def test_security_headers(client):
    r = client.get("/app/")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


# ---- A5 auth
THERAPIST_ROUTES = [
    ("post", "/api/children", {"json": {"name": "X", "age": 4}}),
    ("get", f"/api/children/{KID}", {}),
    ("put", f"/api/children/{KID}", {"json": {"parent_note": "x"}}),
    ("put", f"/api/children/{KID}/clips/kaakka/prompt", {"files": {"audio": ("a.webm", WEBM, "audio/webm")}}),
    ("get", f"/api/children/{KID}/attempts", {}),
    ("patch", "/api/attempts/nope", {"json": {"verdict": "correct"}}),
    ("delete", f"/api/children/{KID}?confirm_name=Kavin", {}),
    ("get", f"/api/children/{KID}/export", {}),
    ("post", "/api/demo/remove", {}),
    ("post", "/api/pin/change", {"json": {"new_pin": "5678"}}),
]


@pytest.mark.parametrize("method,path,kw", THERAPIST_ROUTES)
def test_therapist_routes_need_token(client, method, path, kw):
    assert getattr(client, method)(path, **kw).status_code == 401


def test_pin_lockout_after_five_failures(client):
    for _ in range(4):
        assert client.post("/api/pin", json={"pin": "0000"}).json() == {"ok": False, "locked_for": 0, "pin_is_default": True}
    fifth = client.post("/api/pin", json={"pin": "0000"}).json()
    assert fifth["locked_for"] == 60
    # Even the right PIN is refused while locked.
    assert client.post("/api/pin", json={"pin": "1234"}).json()["ok"] is False


def test_pin_change(therapist):
    assert therapist.post("/api/pin/change", json={"new_pin": "12"}).status_code == 422
    assert therapist.post("/api/pin/change", json={"new_pin": "246810"}).json()["ok"]
    assert therapist.post("/api/pin", json={"pin": "1234"}).json()["ok"] is False
    assert therapist.post("/api/pin", json={"pin": "246810"}).json()["ok"] is True


def test_tampered_token_rejected(therapist):
    tok = therapist.cookies.get("pesu_t")
    therapist.cookies.set("pesu_t", tok[:-2] + ("00" if not tok.endswith("00") else "11"))
    assert therapist.get(f"/api/children/{KID}").status_code == 401


def test_parent_list_hides_therapist_notes(client):
    kid = next(k for k in client.get("/api/children").json() if k["id"] == KID)
    assert "note" not in kid and kid["name"] == "Kavin"


# ---- children
def test_child_validation(therapist):
    assert therapist.post("/api/children", json={"name": "", "age": 4}).status_code == 422
    assert therapist.post("/api/children", json={"name": "A", "age": 1}).status_code == 422
    cid = add_child(therapist)
    assert therapist.put(f"/api/children/{cid}", json={"word_ids": ["kaakka"]}).status_code == 422
    assert therapist.put(f"/api/children/{cid}", json={"word_ids": ["kaakka", "kaakka", "kai"]}).status_code == 422
    ok = therapist.put(f"/api/children/{cid}", json={"word_ids": ["kaakka", "kai", "kaal"], "listen_first": False})
    assert ok.json()["word_ids"] == ["kaakka", "kai", "kaal"]


def test_listen_first_defaults_by_age(therapist):
    young, older = add_child(therapist, "Young", 3), add_child(therapist, "Older", 5)
    assert therapist.get(f"/api/children/{young}/practice").json()["listen_first"] is True
    assert therapist.get(f"/api/children/{older}/practice").json()["listen_first"] is False


# ---- A6 uploads
@pytest.mark.parametrize("blob,mime", [(WEBM, "audio/webm"), (OGG, "audio/ogg"), (MP4, "audio/mp4"), (WAV, "audio/wav")])
def test_clip_upload_sniffs_type(therapist, blob, mime):
    r = therapist.put(f"/api/children/{KID}/clips/kaakka/cue", files={"audio": ("x.webm", blob, "audio/webm")})
    assert r.json()["mime"] == mime
    got = therapist.get(f"/api/children/{KID}/clips/kaakka/cue")
    assert got.headers["content-type"].startswith(mime)


def test_upload_rejects_text_and_oversize(therapist, monkeypatch):
    fake = b"hello, I am not audio" * 200
    r = therapist.put(f"/api/children/{KID}/clips/kaakka/cue", files={"audio": ("x.webm", fake, "audio/webm")})
    assert r.status_code == 415
    monkeypatch.setattr(settings, "max_audio_bytes", 1000)
    r = therapist.put(f"/api/children/{KID}/clips/kaakka/cue", files={"audio": ("x.webm", WEBM, "audio/webm")})
    assert r.status_code == 413


# ---- attempts, A11 audit, D7 agreement
def test_override_audit_trail_and_agreement(therapist):
    aid = save_try(therapist, KID, "correct").json()["id"]
    assert therapist.patch(f"/api/attempts/{aid}", json={"verdict": "error_t", "note": "heard t"}).json()["ok"]
    assert therapist.patch(f"/api/attempts/{aid}", json={"verdict": "unsure"}).json()["ok"]
    data = therapist.get(f"/api/children/{KID}/attempts").json()
    row = next(a for a in data["attempts"] if a["id"] == aid)
    assert row["pesu_verdict"] == "correct" and row["verdict"] == "unsure" and row["decided_by"] == "therapist"
    assert [(e["from_verdict"], e["to_verdict"]) for e in row["events"]] == [("correct", "error_t"), ("error_t", "unsure")]
    assert row["events"][0]["note"] == "heard t"
    assert data["agreement"] == {"agree": 0, "reviewed": 1}
    aid2 = save_try(therapist, KID, "error_t").json()["id"]
    therapist.patch(f"/api/attempts/{aid2}", json={"verdict": "error_t"})  # a confirmation
    assert therapist.get(f"/api/children/{KID}/attempts").json()["agreement"] == {"agree": 1, "reviewed": 2}


def test_parent_decision_is_logged(client):
    r = client.post(
        "/api/attempts",
        data={"child_id": KID, "word_id": "kai", "pesu_verdict": "unsure", "verdict": "correct", "decided_by": "parent"},
    )
    assert r.status_code == 201


def test_unscored_rules(client):
    assert save_try(client, KID, "unscored", decided_by="none").status_code == 201
    assert save_try(client, KID, "unscored", decided_by="pesu").status_code == 422
    assert save_try(client, KID, "correct", decided_by="none").status_code == 422


# ---- A10 summary
def test_summary_counts_scored_only(client):
    sid = client.post("/api/sessions", json={"child_id": KID}).json()["id"]
    for v, by in [("correct", "pesu"), ("error_t", "pesu"), ("unsure", "parent"), ("unscored", "none")]:
        save_try(client, KID, v, decided_by=by, session=sid)
    s = client.get(f"/api/children/{KID}/summary", params={"session_id": sid}).json()
    assert (s["correct"], s["scored"], s["unsure"], s["unscored"], s["scope"]) == (1, 2, 1, 1, "today")


# ---- B13 stickers
def test_one_sticker_per_finished_session(client):
    owned = set(client.get(f"/api/children/{KID}/practice").json()["stickers"])
    sid = client.post("/api/sessions", json={"child_id": KID}).json()["id"]
    save_try(client, KID, "correct", session=sid)
    first = client.patch(f"/api/sessions/{sid}", json={"end_reason": "goal", "stars": 1}).json()
    assert first["sticker_id"] and first["sticker_id"] not in owned
    again = client.patch(f"/api/sessions/{sid}", json={"end_reason": "goal", "stars": 1}).json()
    assert again["already_ended"] and again["sticker_id"] == first["sticker_id"]
    empty = client.post("/api/sessions", json={"child_id": KID}).json()["id"]
    assert client.patch(f"/api/sessions/{empty}", json={"end_reason": "exit", "stars": 0}).json()["sticker_id"] is None


# ---- A14 delete + export
def test_delete_cascades_rows_and_files(therapist):
    cid = add_child(therapist, "Ravi", 5)
    therapist.put(f"/api/children/{cid}/clips/kaakka/prompt", files={"audio": ("a.webm", WEBM, "audio/webm")})
    aid = save_try(therapist, cid, audio=WEBM).json()["id"]
    therapist.patch(f"/api/attempts/{aid}", json={"verdict": "error_t"})
    folder = settings.audio_dir / cid
    assert any(folder.rglob("*.webm"))
    assert therapist.delete(f"/api/children/{cid}", params={"confirm_name": "wrong"}).status_code == 422
    assert therapist.delete(f"/api/children/{cid}", params={"confirm_name": "Ravi"}).json()["ok"]
    assert not folder.exists()
    from app.db import db

    with db() as conn:
        for table in ("attempts", "clips", "sessions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE child_id = ?", (cid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM verdict_events WHERE attempt_id = ?", (aid,)).fetchone()[0] == 0


def test_export_zip_contents(therapist):
    save_try(therapist, KID, audio=WEBM)
    r = therapist.get(f"/api/children/{KID}/export")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert {"attempts.csv", "verdict_events.csv", "sessions.csv", "README.txt"} <= set(names)
    assert any(n.startswith("audio/tries/") for n in names)
    assert "kaakka" in z.read("attempts.csv").decode()


# ---- C9 multi-child isolation
def test_multi_child_isolation(therapist):
    a, b = add_child(therapist, "A1", 4), add_child(therapist, "B1", 4)
    save_try(therapist, a, "correct")
    assert therapist.get(f"/api/children/{b}/attempts").json()["total"] == 0
    assert therapist.get(f"/api/children/{a}/attempts").json()["total"] == 1


# ---- A15 demo data
def test_demo_remove_and_fast_forward(therapist):
    assert therapist.post(f"/api/children/{KID}/demo/fast-forward").json()["added"] > 0
    long = therapist.get(f"/api/children/{KID}/attempts", params={"days": 14}).json()
    assert long["agreement"]["reviewed"] > 0
    assert therapist.post("/api/demo/remove").json()["removed"] == 1
    assert all(k["id"] != KID for k in therapist.get("/api/children").json())


def test_no_demo_seed_when_off(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import auth
    from app.main import app

    monkeypatch.setenv("PESU_DATA_DIR", str(tmp_path / "d2"))
    monkeypatch.setenv("PESU_DEMO", "0")
    settings.reload()
    auth.reset_secret_cache()
    with TestClient(app) as c:
        assert c.get("/api/children").json() == []
        c.post("/api/pin", json={"pin": "1234"})
        assert c.post("/api/demo/remove").status_code == 404


def test_score_endpoint_validates(client):
    assert client.post("/api/score", json={"word_id": "nope"}).status_code == 404
    r = client.post("/api/score", json={"word_id": "kaakka", "alternatives": ["காக்கா"], "confidences": [0.9]})
    assert r.json()["reason"] == "correct"
