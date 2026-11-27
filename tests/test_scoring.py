from app.scoring import score


def v(word, alts, noise=0.0):
    return score(word, alts, noise)["reason"]


def test_correct_tamil():
    assert v("kaakka", ["காக்கா"]) == "correct"


def test_t_substitution_tamil():
    assert v("kaakka", ["டாக்கா"]) == "error_t"
    assert v("kai", ["தை"]) == "error_t"


def test_latin_results():
    assert v("kaakka", ["kaakka"]) == "correct"
    assert v("kaakka", ["taakka"]) == "error_t"


def test_dialect_variant():
    assert v("kozhi", ["கோலி"]) == "correct"


def test_english_word():
    r = score("kaakka", ["crow"])
    assert r["reason"] == "english" and "காக்கா" in r["say_ta"]


def test_silence_noise_multi():
    assert v("kaakka", []) == "silence"
    assert v("kaakka", ["காக்கா"], noise=0.3) == "noise"
    assert v("kaakka", ["காக்கா சொல்லு"]) == "multi"


def test_repeat_is_one_word():
    assert v("kaakka", ["காக்கா காக்கா"]) == "correct"


def test_top_wins_over_autocorrected_lower():
    assert v("kaakka", ["டாக்கா", "காக்கா"]) == "error_t"


def test_unclear_goes_to_parent():
    assert v("kaakka", ["பாப்பா"]) == "unclear"
    assert v("kaakka", ["பாப்பா", "காக்கா", "டாக்கா"]) == "unclear"
