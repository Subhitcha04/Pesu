"""Decides what Pesu heard for one try.

Input: the speech recogniser's alternatives (best first) for ONE try, plus how
loud the room got while listening. Output: a verdict and what Pesu says back.

Pesu only judges one thing: did the word start with the target sound (க / k)
or with the substituted sound (ட, த / t)? Everything it cannot decide cleanly
goes to "unsure", which hands the decision to the parent. It never guesses.

Pitfalls handled here (see README "Scoring pitfalls"):
- Browser recognisers autocorrect towards dictionary words, so a child's
  "taakka" can come back as "காக்கா". We therefore trust the TOP alternative
  first and only fall back to lower alternatives when they all agree.
- Tamil letters are base consonant + vowel sign, so the first code point of a
  word is the consonant we care about (காக்கா -> 'க').
- Children repeat the word ("காக்கா காக்கா"); repeats are one word, not two voices.
"""

from __future__ import annotations

import re
import unicodedata

from .config import settings
from .words import TARGET, WORDS

WORDS_BY_ID = {w["id"]: w for w in WORDS}

MAX_EDIT = 2  # letters of slack allowed when matching a word

# Allowed outputs (checked by the fuzz test).
VERDICTS = {"correct", "error_t", "unsure", "silence", "retry"}
REASONS = {"correct", "error_t", "english", "silence", "multi", "noise", "unclear", "low_conf"}

SAY = {
    "correct": ("சூப்பர்!", "Super!"),
    "error_t": ("இன்னொரு தடவை!", "Innoru thadava!"),
    "english": ("தமிழ்ல சொல்லு: {tamil}!", "Tamil-la sollu: {latin}!"),
    "silence": ("கேக்கல... சத்தமா சொல்லு!", "Kekkala... sathama sollu!"),
    "multi": ("குழந்தை மட்டும் சொல்லட்டும்", "Kuzhandhai mattum sollattum"),
    "noise": ("கொஞ்சம் சத்தமா இருக்கு. TV-ய கம்மி பண்ணலாமா?", "Konjam sathama irukku. TV-ya kammi pannalaama?"),
    "unclear": ("சரியா இருந்துச்சா?", "Sari-yaa irundhucha?"),
    "low_conf": ("சரியா இருந்துச்சா?", "Sari-yaa irundhucha?"),
}

_SPACES = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lower-case and drop punctuation.

    Pitfall: a regex like [^\\w\\s] deletes Tamil vowel signs (Unicode category M),
    turning காக்கா into 'க க க'. Keep letters (L*) and marks (M*) explicitly.
    """
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("‌", "").replace("‍", "")  # zero-width joiners
    kept = [c if unicodedata.category(c)[0] in "LMN" else " " for c in text]
    return _SPACES.sub(" ", "".join(kept)).strip().lower()


def edit_distance(a: str, b: str) -> int:
    """Plain Levenshtein on code points; words here are short, so O(n*m) is fine."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_latin(token: str) -> bool:
    return bool(token) and token[0].isascii()


def _forms(word: dict, latin: bool) -> list[str]:
    if latin:
        return [word["latin"]] + [v for v in word["variants"] if v.isascii()]
    return [word["tamil"]] + [v for v in word["variants"] if not v.isascii()]


def classify_token(token: str, word: dict) -> str:
    """Return 'correct', 'error_t', 'english' or 'other' for one spoken token."""
    if not token:
        return "other"
    if token in word["english"]:
        return "english"
    latin = _is_latin(token)
    forms = _forms(word, latin)
    target = TARGET["target_latin"] if latin else TARGET["target_letter"]
    errors = [TARGET["error_latin"]] if latin else TARGET["error_letters"]

    if token.startswith(target):
        if min(edit_distance(token, f) for f in forms) <= MAX_EDIT:
            return "correct"
        return "other"
    for err in errors:
        if token.startswith(err):
            # Swap the wrong first sound back to the target and see if the rest matches:
            # டாக்கா -> காக்கா is "the right word with t instead of k".
            repaired = target + token[len(err) :]
            if min(edit_distance(repaired, f) for f in forms) <= MAX_EDIT:
                return "error_t"
    return "other"


def classify_alternative(text: str, word: dict) -> tuple[str, bool]:
    """Classify one recogniser alternative. Second value: more than one distinct word heard."""
    tokens = normalise(text).split()
    distinct = list(dict.fromkeys(tokens))  # keeps order, drops repeats
    if not distinct:
        return "empty", False
    labels = [classify_token(t, word) for t in distinct]
    multi = len(distinct) > 1
    # One clear word wins; anything else is mixed.
    for wanted in ("error_t", "correct", "english"):
        if wanted in labels and (not multi or labels.count(wanted) == len(labels)):
            return wanted, False
    return ("other", multi)


def score(
    word_id: str,
    alternatives: list[str],
    noise_rms: float = 0.0,
    confidences: list[float] | None = None,
    min_conf: float | None = None,
) -> dict:
    """Decide one try. Decision order (E1), first match wins:

    1. no text                      -> silence
    2. room noisy while listening   -> unsure (noise)      never "wrong" because of noise
    3. top alternative: >1 word     -> unsure (multi)      usually the parent speaking along
    4. top alternative: k / t       -> correct / error_t   ...unless top confidence < min_conf (low_conf)
    5. top alternative: English     -> retry (english)     "say it in Tamil", not counted
    6. lower alternatives unanimous -> correct / error_t
    7. anything else                -> unsure (unclear)    the parent decides

    Pitfall (A17/E3): Chrome reports confidence 0 for some results (often lower alternatives,
    sometimes all results on Android). 0 means "not reported", not "certain it's wrong", so only
    a positive confidence below min_conf downgrades a verdict. The threshold is not calibrated.
    """
    word = WORDS_BY_ID[word_id]
    min_conf = settings.min_conf if min_conf is None else min_conf
    alts = [a for a in alternatives if normalise(a)]
    confs = list(confidences or [])
    top_conf = confs[0] if confs and alternatives and normalise(alternatives[0]) else None
    result = {"word_id": word_id, "heard": alts[0] if alts else "", "noise_rms": noise_rms, "confidence": top_conf}

    def done(verdict: str, reason: str) -> dict:
        ta, en = SAY[reason]
        result.update(
            verdict=verdict,
            reason=reason,
            say_ta=ta.format(tamil=word["tamil"], latin=word["latin"]),
            say_en=en.format(tamil=word["tamil"], latin=word["latin"]),
        )
        return result

    if not alts:
        return done("silence", "silence")
    if noise_rms >= settings.noise_threshold:
        return done("unsure", "noise")

    top_label, top_multi = classify_alternative(alts[0], word)
    if top_multi:
        return done("unsure", "multi")
    if top_label in ("correct", "error_t"):
        if top_conf is not None and 0 < top_conf < min_conf:
            return done("unsure", "low_conf")
        return done(top_label, top_label)
    if top_label == "english":
        return done("retry", "english")

    # Top result was unclear: only accept the lower alternatives if they all agree.
    lower = {classify_alternative(a, word)[0] for a in alts[1:]} - {"other", "empty"}
    if lower == {"correct"}:
        return done("correct", "correct")
    if lower == {"error_t"}:
        return done("error_t", "error_t")
    return done("unsure", "unclear")
