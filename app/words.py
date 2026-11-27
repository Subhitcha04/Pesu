"""Targets, word bank and stickers. Adding a sound is data + tests, not code (E9).

Each word carries what the scorer and the UI need:
- tamil:     the form the therapist expects
- variants:  dialect and recogniser spellings accepted as the same word (Tamil and Roman, E4)
- english:   English words a child might say instead ("say it in Tamil", not "wrong")
- prompt / cue: default lines, used for text-to-speech only when no therapist clip exists
- picture:   original SVG in app/static/img/words/ (A8/B5); emoji is a fallback only
"""

TARGETS = {
    "k_initial": {
        "id": "k_initial",
        "label": "க sound at the start of a word",
        "target_letter": "க",
        "target_latin": "k",
        # The substitution we listen for: velar fronting, k -> t (ட or த; Roman t / th)
        "error_letters": ["ட", "த"],
        "error_latin": "t",
        "active": True,
    },
    # ர and ழ are listed as "coming soon" in the UI. They need real word banks + tests first.
}
TARGET = TARGETS["k_initial"]

WORDS = [
    {
        "id": "kaakka",
        "tamil": "காக்கா",
        "latin": "kaakka",
        "emoji": "🐦",
        "picture": "kaakka.svg",
        "english": ["crow"],
        "variants": ["காக்கை", "காக்க", "kakka", "kaka", "kaakaa", "kakkaa"],
        "prompt": "காக்கா சொல்லு!",
        "cue": "தொண்டையில இருந்து... க, க!",
    },
    {
        "id": "kai",
        "tamil": "கை",
        "latin": "kai",
        "emoji": "✋",
        "picture": "kai.svg",
        "english": ["hand"],
        "variants": ["கய்", "kay", "kaai", "kaay"],
        "prompt": "கை சொல்லு!",
        "cue": "தொண்டையில இருந்து... க, க... கை!",
    },
    {
        "id": "kozhi",
        "tamil": "கோழி",
        "latin": "kozhi",
        "emoji": "🐔",
        "picture": "kozhi.svg",
        "english": ["hen", "chicken"],
        "variants": ["கோலி", "கோழீ", "koli", "kolli", "kozi", "kozhee"],
        "prompt": "கோழி சொல்லு!",
        "cue": "தொண்டையில இருந்து... கோ, கோ... கோழி!",
    },
    {
        "id": "kudai",
        "tamil": "குடை",
        "latin": "kudai",
        "emoji": "☂️",
        "picture": "kudai.svg",
        "english": ["umbrella"],
        "variants": ["கொடை", "kudae", "kuda", "kodai"],
        "prompt": "குடை சொல்லு!",
        "cue": "தொண்டையில இருந்து... கு, கு... குடை!",
    },
    {
        "id": "kannu",
        "tamil": "கண்ணு",
        "latin": "kannu",
        "emoji": "👁️",
        "picture": "kannu.svg",
        "english": ["eye", "eyes"],
        "variants": ["கண்", "kann", "kanu", "kan"],
        "prompt": "கண்ணு சொல்லு!",
        "cue": "தொண்டையில இருந்து... க, க... கண்ணு!",
    },
    {
        "id": "kaal",
        "tamil": "கால்",
        "latin": "kaal",
        "emoji": "🦶",
        "picture": "kaal.svg",
        "english": ["leg", "foot"],
        "variants": ["காலு", "kal", "kaalu"],
        "prompt": "கால் சொல்லு!",
        "cue": "தொண்டையில இருந்து... கா, கா... கால்!",
    },
]

WORD_IDS = {w["id"] for w in WORDS}

# Original SVG stickers in app/static/img/stickers/ (B13). One new sticker per finished session.
STICKERS = ["sun", "star", "flower", "fish", "leaf", "moon", "balloon", "boat", "butterfly", "kite", "drum", "mango"]

# Praise lines (B12): never the same twice in a row; therapist recordings would take priority.
PRAISE = [
    {"ta": "சூப்பர்!", "en": "Super!"},
    {"ta": "நல்ல க!", "en": "Good k!"},
    {"ta": "கரெக்ட்!", "en": "Correct!"},
    {"ta": "அருமை!", "en": "Wonderful!"},
    {"ta": "சபாஷ்!", "en": "Well done!"},
    {"ta": "வெரி குட்!", "en": "Very good!"},
    {"ta": "செம்ம!", "en": "Awesome!"},
    {"ta": "நல்லா சொன்ன!", "en": "You said it well!"},
]