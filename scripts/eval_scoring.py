"""Run the scorer over tests/golden_scoring.csv and print per-reason precision/recall.

This is a LOGIC REGRESSION SET written by hand from the scoring rules. It is NOT a measure of
real-world accuracy: the inputs are text alternatives, not children's audio.
Usage: python scripts/eval_scoring.py   (exit code 1 if any case fails)
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.scoring import score  # noqa: E402

GOLDEN = Path(__file__).resolve().parent.parent / "tests" / "golden_scoring.csv"


def load() -> list[dict]:
    with GOLDEN.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_case(row: dict) -> str:
    alts = [a for a in row["alternatives"].split("|") if a] if row["alternatives"] else []
    confs = [float(c) for c in row["confidences"].split("|")] if row["confidences"] else None
    return score(row["word_id"], alts, float(row["noise_rms"] or 0), confs, min_conf=0.35)["reason"]


def main() -> int:
    rows = load()
    tp, fp, fn = Counter(), Counter(), Counter()
    failures = []
    for row in rows:
        got, want = run_case(row), row["expected_reason"]
        if got == want:
            tp[want] += 1
        else:
            fp[got] += 1
            fn[want] += 1
            failures.append((row, got))
    print(f"golden cases: {len(rows)}  passed: {len(rows) - len(failures)}  failed: {len(failures)}")
    print(f"{'reason':<10}{'n':>5}{'precision':>11}{'recall':>8}")
    for reason in sorted(set(tp) | set(fn) | set(fp)):
        n = tp[reason] + fn[reason]
        p = tp[reason] / (tp[reason] + fp[reason]) if tp[reason] + fp[reason] else 0.0
        r = tp[reason] / n if n else 0.0
        print(f"{reason:<10}{n:>5}{p:>11.2f}{r:>8.2f}")
    for row, got in failures:
        print(f"FAIL {row['word_id']} {row['alternatives']!r}: expected {row['expected_reason']}, got {got} ({row['note']})")
    print("Note: logic regression set, not a measure of real-world accuracy.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
