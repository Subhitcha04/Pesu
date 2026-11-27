"""E5 golden set (logic regression, not accuracy) and E6 seeded fuzz."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from eval_scoring import load, run_case  # noqa: E402

from app.scoring import REASONS, VERDICTS, normalise, score
from app.words import WORD_IDS

ROWS = load()


def test_golden_set_is_big_enough():
    assert len(ROWS) >= 80


@pytest.mark.parametrize("row", ROWS, ids=[f"{r['word_id']}-{r['note']}-{i}" for i, r in enumerate(ROWS)])
def test_golden(row):
    assert run_case(row) == row["expected_reason"]


ALPHABET = list("கடதஙசஞணநமபயரலவழளறனாிீுூெேைொோௌ்") + list("aktzh ") + ["🐦", "!", "‍", "  ", "crow"]


def random_text(rng: random.Random) -> str:
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 12)))


def test_fuzz_score_never_raises_and_stays_in_bounds():
    rng = random.Random(20261127)
    for _ in range(3000):
        word = rng.choice(sorted(WORD_IDS))
        alts = [random_text(rng) for _ in range(rng.randint(0, 5))]
        confs = [rng.random() for _ in alts] if rng.random() < 0.5 else None
        r1 = score(word, alts, rng.random() * 0.1, confs)
        r2 = score(word, alts, r1["noise_rms"], confs)
        assert r1["verdict"] in VERDICTS and r1["reason"] in REASONS
        assert r1 == r2  # deterministic / idempotent


def test_normalise_is_stable():
    rng = random.Random(7)
    for _ in range(2000):
        t = random_text(rng)
        assert normalise(normalise(t)) == normalise(t)
