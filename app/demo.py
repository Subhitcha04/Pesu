"""Demo data (A15, F21). Only used when PESU_DEMO=1. Everything here is tagged is_sample=1.

- seed_sample_child(): Kavin, 4, with three days of history.
- fast_forward(): 14 days of synthetic history incl. some therapist reviews, so the charts and
  the agreement metric (D7) have something to show. Clearly synthetic: a seeded random generator.
"""

from __future__ import annotations

import json
import random
import sqlite3
import uuid
from datetime import datetime, time, timedelta

from . import timeutil
from .config import settings
from .db import insert
from .words import STICKERS, WORDS

SAMPLE_ID = "kavin-sample"
WORD_BY_ID = {w["id"]: w for w in WORDS}


def _attempt(child_id: str, ts: datetime, word_id: str, verdict: str, session_id: str, decided_by: str = "pesu") -> dict:
    heard = WORD_BY_ID[word_id]["tamil"]
    if verdict == "error_t":
        heard = "ட" + heard[1:]
    return {
        "id": str(uuid.uuid4()),
        "child_id": child_id,
        "session_id": session_id,
        "ts": timeutil.iso(ts),
        "word_id": word_id,
        "pesu_verdict": verdict,
        "verdict": verdict,
        "decided_by": decided_by,
        "reason": verdict,
        "transcript": heard if verdict != "unsure" else "",
        "alternatives": json.dumps([heard]),
        "confidence": 0.8,
        "noise_rms": 0.01,
        "latency_ms": 900,
        "is_sample": 1,
    }


def seed_sample_child(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM children WHERE id = ?", (SAMPLE_ID,)).fetchone():
        return
    words = ["kaakka", "kai", "kozhi", "kudai"]
    insert(
        conn,
        "children",
        {
            "id": SAMPLE_ID,
            "name": "Kavin",
            "age": 4,
            "note": "Fronting: k → t",
            "parent_note": "கோழி-க்கு கொஞ்சம் அதிகமா practice பண்ணுங்க",
            "word_ids": json.dumps(words),
            "sessions_per_day": 2,
            "tries_per_session": 7,
            "is_sample": 1,
            "created_at": timeutil.now_iso(),
        },
    )
    # Day -3: 2/7, Day -2: 3/7, Day -1: 4/7 -> a visible upward trend.
    pattern = {3: [1, 0, 0, 1, 0, 0, 0], 2: [1, 0, 1, 0, 1, 0, 0], 1: [1, 1, 0, 1, 0, 1, 0]}
    for days_ago, results in pattern.items():
        day = timeutil.today_local() - timedelta(days=days_ago)
        start = datetime.combine(day, time(18, 0), tzinfo=settings.tz)
        sid = f"sample-{days_ago}"
        insert(
            conn,
            "sessions",
            {
                "id": sid,
                "child_id": SAMPLE_ID,
                "started_at": timeutil.iso(start),
                "ended_at": timeutil.iso(start + timedelta(minutes=5)),
                "end_reason": "goal",
                "stars": sum(results),
                "sticker_id": STICKERS[3 - days_ago],
                "is_sample": 1,
            },
        )
        for i, ok in enumerate(results):
            insert(
                conn,
                "attempts",
                _attempt(
                    SAMPLE_ID,
                    start + timedelta(minutes=i % 6, seconds=i),
                    words[i % len(words)],
                    "correct" if ok else "error_t",
                    sid,
                ),
            )


def fast_forward(conn: sqlite3.Connection, child_id: str, days: int = 14) -> int:
    """Add `days` of synthetic sessions before today with a slowly improving success rate."""
    child = conn.execute("SELECT word_ids FROM children WHERE id = ?", (child_id,)).fetchone()
    words = json.loads(child["word_ids"]) or ["kaakka"]
    rng = random.Random(42)
    added = 0
    for d in range(days, 3, -1):  # leave the last 3 days to the real seed
        day = timeutil.today_local() - timedelta(days=d)
        if rng.random() < 0.2:  # rest days are allowed
            continue
        start = datetime.combine(day, time(17 + rng.randint(0, 3), rng.randint(0, 59)), tzinfo=settings.tz)
        sid = f"ff-{child_id}-{d}"
        if conn.execute("SELECT 1 FROM sessions WHERE id = ?", (sid,)).fetchone():
            continue
        p_correct = 0.25 + 0.03 * (days - d)
        insert(
            conn,
            "sessions",
            {
                "id": sid,
                "child_id": child_id,
                "started_at": timeutil.iso(start),
                "ended_at": timeutil.iso(start + timedelta(minutes=5)),
                "end_reason": "goal",
                "stars": 0,
                "is_sample": 1,
            },
        )
        for i in range(7):
            roll = rng.random()
            verdict = "correct" if roll < p_correct else ("unsure" if roll > 0.93 else "error_t")
            row = _attempt(
                child_id,
                start + timedelta(seconds=40 * i),
                words[i % len(words)],
                verdict,
                sid,
                decided_by="parent" if verdict == "unsure" else "pesu",
            )
            insert(conn, "attempts", row)
            added += 1
            # The therapist reviewed about half of the definite tries; she disagreed with ~1 in 6.
            if verdict != "unsure" and rng.random() < 0.5:
                final = verdict if rng.random() > 0.16 else ("error_t" if verdict == "correct" else "correct")
                conn.execute("UPDATE attempts SET verdict = ?, decided_by = 'therapist' WHERE id = ?", (final, row["id"]))
                insert(
                    conn,
                    "verdict_events",
                    {
                        "attempt_id": row["id"],
                        "ts": row["ts"],
                        "actor": "therapist",
                        "from_verdict": verdict,
                        "to_verdict": final,
                        "note": "sample review",
                    },
                )
    return added
