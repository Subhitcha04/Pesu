"""Pesu API: children, weekly targets, therapist clips, scoring, attempts, sessions, review.

Runs with no secret keys. Speech recognition happens in the browser (Web Speech API, ta-IN);
this server stores data, scores tries and serves the UI.

Route groups:
- open (parent / child device): config, child list, practice payload, scoring, saving tries,
  sessions, summary, audio playback.
- therapist (signed cookie, see auth.py): setup, clips upload, review, overrides, delete, export, demo tools.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import timedelta
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, demo, scoring, timeutil
from .audio import safe_path, save_audio
from .config import ROOT, VERSION, settings
from .db import db, insert, migrate, schema_version, update
from .words import PRAISE, STICKERS, TARGET, WORD_IDS, WORDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pesu")

STATIC_DIR = ROOT / "app" / "static"
Therapist = Annotated[None, Depends(auth.require_therapist)]


class Verdict(StrEnum):
    correct = "correct"
    error_t = "error_t"
    unsure = "unsure"
    unscored = "unscored"


# ---------------------------------------------------------------- startup
def apply_retention() -> int:
    """F6: delete child audio older than PESU_AUDIO_RETENTION_DAYS; verdict rows are kept."""
    cutoff = timeutil.iso(timeutil.now() - timedelta(days=settings.retention_days))
    removed = 0
    with db() as conn:
        rows = conn.execute("SELECT id, audio_path FROM attempts WHERE audio_path IS NOT NULL AND ts < ?", (cutoff,)).fetchall()
        for r in rows:
            try:
                safe_path(r["audio_path"]).unlink(missing_ok=True)
            except HTTPException:
                pass
            conn.execute("UPDATE attempts SET audio_path = NULL, audio_mime = NULL WHERE id = ?", (r["id"],))
            removed += 1
    return removed


def startup() -> None:
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    version = migrate()
    if settings.demo:
        with db() as conn:
            demo.seed_sample_child(conn)
    removed = apply_retention()
    auth.secret()
    if auth.pin_is_default():
        log.warning("Therapist PIN is still the default from PESU_THERAPIST_PIN. Change it in the app.")
    log.info(
        "Pesu %s ready: schema v%s, demo=%s, tz=%s, old audio removed=%s",
        VERSION,
        version,
        settings.demo,
        settings.tz_name,
        removed,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    startup()
    yield


app = FastAPI(title="Pesu", version=VERSION, lifespan=lifespan)

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """F4. Pitfall: style-src keeps 'unsafe-inline' because templates set inline style attributes;
    scripts are strictly 'self' (no inline handlers anywhere)."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------- helpers
def child_or_404(conn, child_id: str):
    row = conn.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Child not found")
    return row


def child_json(row) -> dict:
    d = dict(row)
    d["word_ids"] = json.loads(d["word_ids"] or "[]")
    d["is_sample"] = bool(d["is_sample"])
    return d


def today_stats(conn, child) -> dict:
    start = timeutil.day_start_utc(timeutil.today_local())
    rows = conn.execute("SELECT verdict FROM attempts WHERE child_id = ? AND ts >= ?", (child["id"], start)).fetchall()
    return {
        "tries": len(rows),
        "correct": sum(r["verdict"] == "correct" for r in rows),
        "goal": child["sessions_per_day"] * child["tries_per_session"],
        # Only sessions the child actually finished count towards "enough for today" (B23).
        "sessions": conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE child_id = ? AND started_at >= ? AND end_reason IN ('goal', 'finished')",
            (child["id"], start),
        ).fetchone()[0],
    }


def week_dots(conn, child_id: str) -> list[dict]:
    """C2: which of the last 7 local days had any practice (no fragile consecutive streaks)."""
    days = timeutil.last_n_days(7)
    since = timeutil.day_start_utc(days[0])
    practised = {
        timeutil.local_day(r["ts"])
        for r in conn.execute("SELECT ts FROM attempts WHERE child_id = ? AND ts >= ?", (child_id, since))
    }
    return [{"day": d.isoformat(), "practised": d.isoformat() in practised} for d in days]


def clip_coverage(conn, child) -> dict:
    have = {(r["word_id"], r["kind"]) for r in conn.execute("SELECT word_id, kind FROM clips WHERE child_id = ?", (child["id"],))}
    words = json.loads(child["word_ids"])
    return {
        "prompts": sum((w, "prompt") in have for w in words),
        "cues": sum((w, "cue") in have for w in words),
        "total": len(words),
        "have": sorted(f"{w}:{k}" for w, k in have),
    }


def word_success(conn, child_id: str, days: int = 7) -> dict:
    since = timeutil.day_start_utc(timeutil.last_n_days(days)[0])
    stats: dict[str, list[int]] = {}
    for r in conn.execute(
        "SELECT word_id, verdict FROM attempts WHERE child_id = ? AND ts >= ? AND verdict IN ('correct','error_t')",
        (child_id, since),
    ):
        s = stats.setdefault(r["word_id"], [0, 0])
        s[0] += r["verdict"] == "correct"
        s[1] += 1
    return {w: {"correct": c, "scored": n} for w, (c, n) in stats.items()}


# ---------------------------------------------------------------- config + auth
@app.get("/api/health")
def health() -> dict:
    writable = True
    try:
        with db() as conn:
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS _w (x)")
    except Exception:
        writable = False
    return {
        "ok": writable,
        "version": VERSION,
        "schema_version": schema_version(),
        "db_writable": writable,
        "demo": settings.demo,
    }


@app.get("/api/config")
def config() -> dict:
    return {
        "target": TARGET,
        "words": WORDS,
        "noise_threshold": settings.noise_threshold,
        "demo": settings.demo,
        "stickers": STICKERS,
        "praise": PRAISE,
        "tz": settings.tz_name,
        "min_conf": settings.min_conf,
        "version": VERSION,
        "retention_days": settings.retention_days,
    }


class PinIn(BaseModel):
    pin: str = Field(min_length=1, max_length=12)


@app.post("/api/pin")
def check_pin(body: PinIn, response: Response) -> dict:
    result = auth.verify_pin(body.pin)
    if result["ok"]:
        auth.set_cookie(response)
    return {**result, "pin_is_default": auth.pin_is_default()}


@app.post("/api/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth")
def auth_status(request: Request) -> dict:
    return {"therapist": auth.check_token(request.cookies.get(auth.COOKIE)), "pin_is_default": auth.pin_is_default()}


class PinChange(BaseModel):
    new_pin: str = Field(pattern=r"^\d{4,6}$")


@app.post("/api/pin/change")
def pin_change(body: PinChange, _: Therapist) -> dict:
    auth.change_pin(body.new_pin)
    return {"ok": True}


# ---------------------------------------------------------------- children
class ChildIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    age: int = Field(ge=2, le=12)
    note: str = Field(default="", max_length=200)


class ChildUpdate(BaseModel):
    word_ids: list[str] | None = None
    sessions_per_day: int | None = Field(default=None, ge=1, le=3)
    tries_per_session: int | None = Field(default=None, ge=3, le=12)
    parent_note: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=200)
    listen_first: bool | None = None


@app.get("/api/children")
def list_children(request: Request) -> list[dict]:
    """Open list for the parent picker: no therapist notes unless the caller is the therapist."""
    is_therapist = auth.check_token(request.cookies.get(auth.COOKIE))
    with db() as conn:
        out = []
        for r in conn.execute("SELECT * FROM children ORDER BY is_sample DESC, created_at"):
            d = {
                "id": r["id"],
                "name": r["name"],
                "age": r["age"],
                "is_sample": bool(r["is_sample"]),
                "today": today_stats(conn, r),
            }
            if is_therapist:
                last = conn.execute("SELECT MAX(ts) FROM attempts WHERE child_id = ?", (r["id"],)).fetchone()[0]
                needs = conn.execute(
                    "SELECT COUNT(*) FROM attempts a WHERE a.child_id = ? AND a.verdict IN ('unsure','unscored') "
                    "AND NOT EXISTS (SELECT 1 FROM verdict_events e WHERE e.attempt_id = a.id AND e.actor='therapist')",
                    (r["id"],),
                ).fetchone()[0]
                d.update(
                    note=r["note"],
                    last_practised=timeutil.local_day(last) if last else None,
                    needs_review=needs,
                    word_ids=json.loads(r["word_ids"]),
                )
            out.append(d)
        return out


@app.post("/api/children", status_code=201)
def add_child(body: ChildIn, _: Therapist) -> dict:
    cid = uuid.uuid4().hex[:10]
    with db() as conn:
        insert(
            conn,
            "children",
            {
                "id": cid,
                "name": body.name.strip(),
                "age": body.age,
                "note": body.note,
                "word_ids": json.dumps(["kaakka", "kai", "kozhi"]),
                "created_at": timeutil.now_iso(),
            },
        )
        return child_json(child_or_404(conn, cid))


@app.get("/api/children/{child_id}")
def get_child(child_id: str, _: Therapist) -> dict:
    with db() as conn:
        row = child_or_404(conn, child_id)
        d = child_json(row)
        d["today"] = today_stats(conn, row)
        d["coverage"] = clip_coverage(conn, row)
        return d


@app.put("/api/children/{child_id}")
def update_child(child_id: str, body: ChildUpdate, _: Therapist) -> dict:
    fields = body.model_dump(exclude_none=True)
    if "word_ids" in fields:
        bad = set(fields["word_ids"]) - WORD_IDS
        if bad or not 3 <= len(fields["word_ids"]) <= 6 or len(set(fields["word_ids"])) != len(fields["word_ids"]):
            raise HTTPException(422, "Pick 3 to 6 different words from the word bank")
        fields["word_ids"] = json.dumps(fields["word_ids"])
    if "listen_first" in fields:
        fields["listen_first"] = int(fields["listen_first"])
    with db() as conn:
        child_or_404(conn, child_id)
        update(
            conn,
            "children",
            {"id": child_id},
            fields,
            allowed={"word_ids", "sessions_per_day", "tries_per_session", "parent_note", "note", "listen_first"},
        )
        return child_json(child_or_404(conn, child_id))


@app.get("/api/children/{child_id}/practice")
def practice_payload(child_id: str) -> dict:
    """Everything the parent/child screens need, and nothing more (no therapist notes)."""
    with db() as conn:
        row = child_or_404(conn, child_id)
        stickers = [
            r["sticker_id"]
            for r in conn.execute(
                "SELECT sticker_id FROM sessions WHERE child_id = ? AND sticker_id IS NOT NULL ORDER BY started_at", (child_id,)
            )
        ]
        last = conn.execute(
            "SELECT * FROM sessions WHERE child_id = ? AND ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1", (child_id,)
        ).fetchone()
        listen_first = row["listen_first"]
        return {
            "id": row["id"],
            "name": row["name"],
            "age": row["age"],
            "is_sample": bool(row["is_sample"]),
            "word_ids": json.loads(row["word_ids"]),
            "tries_per_session": row["tries_per_session"],
            "sessions_per_day": row["sessions_per_day"],
            "parent_note": row["parent_note"],
            "listen_first": bool(listen_first) if listen_first is not None else row["age"] <= 3,
            "today": today_stats(conn, row),
            "week": week_dots(conn, child_id),
            "coverage": clip_coverage(conn, row),
            "word_success": word_success(conn, child_id),
            "stickers": stickers,
            "last_session": dict(last) if last else None,
        }


# ---------------------------------------------------------------- therapist clips
@app.put("/api/children/{child_id}/clips/{word_id}/{kind}")
async def upload_clip(child_id: str, word_id: str, kind: str, _: Therapist, audio: UploadFile = File(...)) -> dict:
    if word_id not in WORD_IDS or kind not in {"prompt", "cue"}:
        raise HTTPException(404, "Unknown word or clip kind")
    with db() as conn:
        child_or_404(conn, child_id)
    rel, mime = await save_audio(audio, settings.audio_dir / child_id / "clips", f"{word_id}-{kind}")
    with db() as conn:
        conn.execute(
            "INSERT INTO clips (child_id, word_id, kind, path, mime, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(child_id, word_id, kind) DO UPDATE SET path=excluded.path, mime=excluded.mime, "
            "updated_at=excluded.updated_at",
            (child_id, word_id, kind, rel, mime, timeutil.now_iso()),
        )
    return {"ok": True, "mime": mime}


@app.get("/api/children/{child_id}/clips/{word_id}/{kind}")
def get_clip(child_id: str, word_id: str, kind: str):
    with db() as conn:
        row = conn.execute(
            "SELECT path, mime FROM clips WHERE child_id=? AND word_id=? AND kind=?", (child_id, word_id, kind)
        ).fetchone()
    if not row:
        raise HTTPException(404, "No clip recorded")
    return FileResponse(safe_path(row["path"]), media_type=row["mime"])


# ---------------------------------------------------------------- scoring + sessions + attempts
class ScoreIn(BaseModel):
    word_id: str
    alternatives: list[str] = Field(default=[], max_length=10)
    confidences: list[float] = Field(default=[], max_length=10)
    noise_rms: float = Field(default=0.0, ge=0, le=1)


@app.post("/api/score")
def score_try(body: ScoreIn) -> dict:
    if body.word_id not in WORD_IDS:
        raise HTTPException(404, "Unknown word")
    alts = [a[:200] for a in body.alternatives]
    return scoring.score(body.word_id, alts, body.noise_rms, body.confidences)


class SessionIn(BaseModel):
    child_id: str


class SessionEnd(BaseModel):
    end_reason: str = Field(pattern=r"^(goal|finished|paused|exit|time_cap|prompt_cap|silence)$")
    stars: int = Field(ge=0, le=50)


@app.post("/api/sessions", status_code=201)
def start_session(body: SessionIn) -> dict:
    sid = uuid.uuid4().hex[:12]
    with db() as conn:
        child_or_404(conn, body.child_id)
        insert(conn, "sessions", {"id": sid, "child_id": body.child_id, "started_at": timeutil.now_iso()})
    return {"id": sid}


@app.patch("/api/sessions/{session_id}")
def end_session(session_id: str, body: SessionEnd) -> dict:
    """Ends a session. B13: a session the child finished earns one new sticker (never more, never lost)."""
    with db() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not s:
            raise HTTPException(404, "Session not found")
        if s["ended_at"]:
            return {"sticker_id": s["sticker_id"], "already_ended": True}
        tries = conn.execute("SELECT COUNT(*) FROM attempts WHERE session_id = ?", (session_id,)).fetchone()[0]
        sticker = None
        if body.end_reason in {"goal", "finished"} and tries > 0:
            owned = {
                r["sticker_id"]
                for r in conn.execute(
                    "SELECT sticker_id FROM sessions WHERE child_id = ? AND sticker_id IS NOT NULL", (s["child_id"],)
                )
            }
            sticker = next((x for x in STICKERS if x not in owned), None)
        conn.execute(
            "UPDATE sessions SET ended_at = ?, end_reason = ?, stars = ?, sticker_id = ? WHERE id = ?",
            (timeutil.now_iso(), body.end_reason, body.stars, sticker, session_id),
        )
    return {"sticker_id": sticker, "already_ended": False}


@app.post("/api/attempts", status_code=201)
async def save_attempt(
    child_id: str = Form(...),
    word_id: str = Form(...),
    session_id: str = Form(""),
    pesu_verdict: str = Form(...),
    verdict: Verdict = Form(...),
    decided_by: str = Form("pesu"),
    reason: str = Form("", max_length=20),
    transcript: str = Form("", max_length=200),
    alternatives: str = Form("[]", max_length=2000),
    confidence: float | None = Form(None),
    noise_rms: float = Form(0.0),
    latency_ms: int | None = Form(None),
    audio: UploadFile | None = File(None),
) -> dict:
    if decided_by not in {"pesu", "parent", "none"} or word_id not in WORD_IDS:
        raise HTTPException(422, "Bad decider or word")
    if (verdict == Verdict.unscored) != (decided_by == "none"):
        raise HTTPException(422, "unscored tries are decided by nobody")
    try:
        alts = json.loads(alternatives)
        assert isinstance(alts, list)
    except Exception:
        raise HTTPException(422, "alternatives must be a JSON list") from None
    with db() as conn:
        child_or_404(conn, child_id)
    aid = str(uuid.uuid4())
    rel = mime = None
    if audio is not None:
        rel, mime = await save_audio(audio, settings.audio_dir / child_id / "tries", aid)
    with db() as conn:
        insert(
            conn,
            "attempts",
            {
                "id": aid,
                "child_id": child_id,
                "session_id": session_id or None,
                "ts": timeutil.now_iso(),
                "word_id": word_id,
                "pesu_verdict": pesu_verdict,
                "verdict": verdict.value,
                "decided_by": decided_by,
                "reason": reason,
                "transcript": transcript,
                "alternatives": json.dumps(alts[:10]),
                "confidence": confidence,
                "noise_rms": noise_rms,
                "latency_ms": latency_ms,
                "audio_path": rel,
                "audio_mime": mime,
                "is_sample": 0,
            },
        )
        if decided_by == "parent":
            insert(
                conn,
                "verdict_events",
                {
                    "attempt_id": aid,
                    "ts": timeutil.now_iso(),
                    "actor": "parent",
                    "from_verdict": pesu_verdict,
                    "to_verdict": verdict.value,
                    "note": "",
                },
            )
    return {"id": aid}


@app.get("/api/attempts/{attempt_id}/audio")
def attempt_audio(attempt_id: str):
    with db() as conn:
        row = conn.execute("SELECT audio_path, audio_mime FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if not row or not row["audio_path"]:
        raise HTTPException(404, "No audio for this try")
    return FileResponse(safe_path(row["audio_path"]), media_type=row["audio_mime"] or "audio/webm")


@app.get("/api/children/{child_id}/summary")
def summary(child_id: str, session_id: str | None = None) -> dict:
    """A10/C5: counts for the parent. Denominator = scored tries only; unsure/unscored reported apart."""
    with db() as conn:
        child_or_404(conn, child_id)
        if session_id:
            rows = conn.execute(
                "SELECT * FROM attempts WHERE child_id = ? AND session_id = ? ORDER BY ts", (child_id, session_id)
            ).fetchall()
            first = rows[0]["ts"] if rows else timeutil.now_iso()
            scope = "today" if timeutil.local_day(first) == timeutil.today_local().isoformat() else "that_day"
        else:
            rows = conn.execute(
                "SELECT * FROM attempts WHERE child_id = ? AND ts >= ? ORDER BY ts",
                (child_id, timeutil.day_start_utc(timeutil.today_local())),
            ).fetchall()
            scope = "today"
    verdicts = [r["verdict"] for r in rows]
    return {
        "scope": scope,
        "sound": TARGET["target_letter"],
        "correct": verdicts.count("correct"),
        "scored": verdicts.count("correct") + verdicts.count("error_t"),
        "unsure": verdicts.count("unsure"),
        "unscored": verdicts.count("unscored"),
        "parent_decided": sum(r["decided_by"] == "parent" for r in rows),
        "items": [
            {
                "id": r["id"],
                "word_id": r["word_id"],
                "verdict": r["verdict"],
                "decided_by": r["decided_by"],
                "has_audio": bool(r["audio_path"]),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------- therapist review
class Override(BaseModel):
    verdict: Verdict
    note: str = Field(default="", max_length=200)


@app.get("/api/children/{child_id}/attempts")
def list_attempts(child_id: str, _: Therapist, days: int = 7) -> dict:
    days = max(1, min(days, 90))
    day_list = timeutil.last_n_days(days)
    since = timeutil.day_start_utc(day_list[0])
    with db() as conn:
        child_or_404(conn, child_id)
        rows = [
            dict(r)
            for r in conn.execute("SELECT * FROM attempts WHERE child_id = ? AND ts >= ? ORDER BY ts DESC", (child_id, since))
        ]
        events: dict[str, list[dict]] = {}
        for e in conn.execute(
            "SELECT e.* FROM verdict_events e JOIN attempts a ON a.id = e.attempt_id "
            "WHERE a.child_id = ? AND a.ts >= ? ORDER BY e.id",
            (child_id, since),
        ):
            events.setdefault(e["attempt_id"], []).append(dict(e))
    per_day = {d.isoformat(): {"day": d.isoformat(), "tries": 0, "correct": 0, "scored": 0} for d in day_list}
    per_word: dict[str, dict] = {}
    agree = reviewed = 0
    trouble: dict[str, int] = {}
    counts = {v.value: 0 for v in Verdict}
    for r in rows:
        r["has_audio"] = bool(r.pop("audio_path"))
        r.pop("audio_mime", None)
        r["alternatives"] = json.loads(r["alternatives"] or "[]")
        r["is_sample"] = bool(r["is_sample"])
        r["local_day"] = timeutil.local_day(r["ts"])
        r["events"] = events.get(r["id"], [])
        r["therapist_reviewed"] = any(e["actor"] == "therapist" for e in r["events"])
        counts[r["verdict"]] += 1
        d = per_day.get(r["local_day"])
        if d:
            d["tries"] += 1
            d["correct"] += r["verdict"] == "correct"
            d["scored"] += r["verdict"] in ("correct", "error_t")
        w = per_word.setdefault(r["word_id"], {"word_id": r["word_id"], "correct": 0, "scored": 0, "agree": 0, "reviewed": 0})
        if r["verdict"] in ("correct", "error_t"):
            w["scored"] += 1
            w["correct"] += r["verdict"] == "correct"
        if r["verdict"] == "error_t":
            trouble[r["word_id"]] = trouble.get(r["word_id"], 0) + 1
        # D7: agreement between Pesu's first pass and the therapist's final verdict.
        if r["therapist_reviewed"] and r["pesu_verdict"] in ("correct", "error_t"):
            reviewed += 1
            w["reviewed"] += 1
            if r["pesu_verdict"] == r["verdict"]:
                agree += 1
                w["agree"] += 1
    scored = counts["correct"] + counts["error_t"]
    return {
        "attempts": rows,
        "days": list(per_day.values()),
        "per_word": list(per_word.values()),
        "counts": counts,
        "total": len(rows),
        "scored": scored,
        "correct": counts["correct"],
        "most_trouble": max(trouble, key=trouble.get) if trouble else None,
        "agreement": {"agree": agree, "reviewed": reviewed},
    }


@app.patch("/api/attempts/{attempt_id}")
def override_attempt(attempt_id: str, body: Override, _: Therapist) -> dict:
    """A11: sets the therapist's verdict and appends it to the audit trail; pesu_verdict never changes.

    Confirming the same verdict is recorded too (it counts as a review for the agreement metric)."""
    if body.verdict == Verdict.unscored:
        raise HTTPException(422, "The therapist sets correct, error_t or unsure")
    with db() as conn:
        row = conn.execute("SELECT verdict FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Attempt not found")
        insert(
            conn,
            "verdict_events",
            {
                "attempt_id": attempt_id,
                "ts": timeutil.now_iso(),
                "actor": "therapist",
                "from_verdict": row["verdict"],
                "to_verdict": body.verdict.value,
                "note": body.note,
            },
        )
        conn.execute("UPDATE attempts SET verdict = ?, decided_by = 'therapist' WHERE id = ?", (body.verdict.value, attempt_id))
    return {"ok": True}


@app.delete("/api/children/{child_id}")
def delete_child(child_id: str, confirm_name: str, _: Therapist) -> dict:
    """A14: rows cascade via foreign keys; the child's audio folder is removed from disk."""
    with db() as conn:
        row = child_or_404(conn, child_id)
        if confirm_name.strip() != row["name"]:
            raise HTTPException(422, "Type the child's name exactly to confirm")
        conn.execute("DELETE FROM children WHERE id = ?", (child_id,))
    folder = settings.audio_dir / child_id
    if folder.exists():
        shutil.rmtree(folder)
    return {"ok": True}


def _csv(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


@app.get("/api/children/{child_id}/export")
def export_child(child_id: str, _: Therapist) -> StreamingResponse:
    """A14: ZIP with attempts.csv, verdict_events.csv, sessions.csv, audio/ and README.txt."""
    with db() as conn:
        child = child_or_404(conn, child_id)
        attempts = [dict(r) for r in conn.execute("SELECT * FROM attempts WHERE child_id = ? ORDER BY ts", (child_id,))]
        events = [
            dict(r)
            for r in conn.execute(
                "SELECT e.* FROM verdict_events e JOIN attempts a ON a.id = e.attempt_id WHERE a.child_id = ? ORDER BY e.id",
                (child_id,),
            )
        ]
        sessions = [dict(r) for r in conn.execute("SELECT * FROM sessions WHERE child_id = ? ORDER BY started_at", (child_id,))]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "attempts.csv",
            _csv(
                attempts,
                [
                    "id",
                    "ts",
                    "word_id",
                    "pesu_verdict",
                    "verdict",
                    "decided_by",
                    "reason",
                    "transcript",
                    "confidence",
                    "noise_rms",
                    "latency_ms",
                    "session_id",
                    "audio_path",
                    "is_sample",
                ],
            ),
        )
        z.writestr("verdict_events.csv", _csv(events, ["id", "attempt_id", "ts", "actor", "from_verdict", "to_verdict", "note"]))
        z.writestr(
            "sessions.csv", _csv(sessions, ["id", "started_at", "ended_at", "end_reason", "stars", "sticker_id", "is_sample"])
        )
        folder = settings.audio_dir / child_id
        for f in sorted(folder.rglob("*")) if folder.exists() else []:
            if f.is_file():
                z.write(f, "audio/" + str(f.relative_to(folder)))
        z.writestr(
            "README.txt",
            (
                f"Pesu export for {child['name']} (age {child['age']}), created {timeutil.now_iso()}.\n"
                "attempts.csv: every try. ts is UTC. pesu_verdict is Pesu's first pass; verdict is the final one.\n"
                "verdict_events.csv: who changed a verdict, when, and why.\n"
                "sessions.csv: practice sessions and stickers earned.\n"
                "audio/: therapist clips (clips/) and the child's tries (tries/, named by attempt id).\n"
            ),
        )
    buf.seek(0)
    name = f"pesu-{child['name']}-{timeutil.today_local().isoformat()}.zip".replace(" ", "_")
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- demo tools (PESU_DEMO=1 only)
def _require_demo() -> None:
    if not settings.demo:
        raise HTTPException(404, "Demo mode is off")


@app.post("/api/demo/remove")
def demo_remove(_: Therapist) -> dict:
    _require_demo()
    with db() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM children WHERE is_sample = 1")]
        conn.execute("DELETE FROM children WHERE is_sample = 1")
        conn.execute("DELETE FROM attempts WHERE is_sample = 1")
        conn.execute("DELETE FROM sessions WHERE is_sample = 1")
    for cid in ids:
        shutil.rmtree(settings.audio_dir / cid, ignore_errors=True)
    return {"removed": len(ids)}


@app.post("/api/children/{child_id}/demo/fast-forward")
def demo_fast_forward(child_id: str, _: Therapist) -> dict:
    _require_demo()
    with db() as conn:
        child_or_404(conn, child_id)
        added = demo.fast_forward(conn, child_id)
    return {"added": added}


# ---------------------------------------------------------------- UI
@app.get("/")
def index():
    return RedirectResponse("/app/")


app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="static")
