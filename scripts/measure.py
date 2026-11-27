"""Measure the numbers quoted in the README "Performance & footprint" section.

Starts a fresh server in a temp dir, then: cold start time, /api/score latency over 1,000 local
calls (p50/p95), DB growth per 1,000 tries (no audio), and the size of the static front end.
Usage: python scripts/measure.py
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.e2e.conftest import start_server  # noqa: E402


def main() -> None:
    data = Path(tempfile.mkdtemp())
    t0 = time.perf_counter()
    proc, base = start_server(data, demo=False)
    cold = time.perf_counter() - t0
    try:
        c = httpx.Client(base_url=base)
        body = {"word_id": "kaakka", "alternatives": ["டாக்கா", "காக்கா"], "confidences": [0.8, 0], "noise_rms": 0.01}
        for _ in range(50):
            c.post("/api/score", json=body)  # warm-up
        lat = []
        for _ in range(1000):
            s = time.perf_counter()
            c.post("/api/score", json=body)
            lat.append((time.perf_counter() - s) * 1000)
        lat.sort()
        c.post("/api/pin", json={"pin": "1234"})
        kid = c.post("/api/children", json={"name": "Bench", "age": 4}).json()["id"]
        db = data / "pesu.db"
        wal = data / "pesu.db-wal"
        size = lambda: db.stat().st_size + (wal.stat().st_size if wal.exists() else 0)  # noqa: E731
        before = size()
        for i in range(1000):
            c.post(
                "/api/attempts",
                data={
                    "child_id": kid,
                    "word_id": "kai",
                    "pesu_verdict": "correct",
                    "verdict": "correct",
                    "decided_by": "pesu",
                    "transcript": "கை",
                    "alternatives": '["கை"]',
                    "session_id": f"s{i // 7}",
                },
            )
        c.post("/api/logout")
        growth = size() - before
    finally:
        proc.terminate()
    static = ROOT / "app" / "static"
    js = sum(f.stat().st_size for f in static.rglob("*.js"))
    css = sum(f.stat().st_size for f in static.rglob("*.css"))
    fonts = sum(f.stat().st_size for f in static.rglob("*.woff2"))
    svgs = sum(f.stat().st_size for f in static.rglob("*.svg"))
    print(f"cold start (process start -> /api/health 200): {cold:.2f} s")
    print(
        f"/api/score latency, 1000 sequential local calls: p50 {statistics.median(lat):.2f} ms, "
        f"p95 {lat[int(0.95 * len(lat)) - 1]:.2f} ms"
    )
    print(f"database growth for 1000 tries without audio: {growth / 1024:.0f} KB")
    print(
        f"front end (uncompressed): JS {js / 1024:.1f} KB, CSS {css / 1024:.1f} KB, "
        f"fonts {fonts / 1024:.1f} KB, SVG art {svgs / 1024:.1f} KB"
    )


if __name__ == "__main__":
    main()
