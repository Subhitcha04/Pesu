"""End-to-end practice flow through the real UI (F16). Uses Judge Mode or a stubbed recogniser."""

from __future__ import annotations

import time

import pytest

from tests.e2e.conftest import therapist_api

KID = "kavin-sample"


def start_practice(page, child=KID):
    page.goto(f"/app/#/p/{child}")
    page.click("#start")
    page.wait_for_selector(".stage[data-phase=listen]", timeout=15000)


def sim(page, kind):
    """Wait for the child's turn, then press a Judge Mode button."""
    page.wait_for_selector(".stage[data-phase=listen]", timeout=15000)
    page.click(f"[data-sim={kind}]")
    page.wait_for_function("() => document.getElementById('stage')?.dataset.phase !== 'listen'", timeout=10000)


def attempts(base, child=KID):
    return therapist_api(base).get(f"/api/children/{child}/attempts", params={"days": 1}).json()["attempts"]


def test_correct_try_earns_a_star(page):
    before = len(attempts(page.base))
    start_practice(page)
    sim(page, "right")
    page.locator("#stars", has_text="1").wait_for(timeout=10000)
    rows = attempts(page.base)
    assert len(rows) == before + 1 and rows[0]["verdict"] == "correct" and rows[0]["decided_by"] == "pesu"


def test_t_error_twice_then_next_picture(page):
    start_practice(page)
    first = page.get_attribute("#picbtn img", "src")
    sim(page, "t")
    page.locator(".stage.tilt").wait_for(timeout=5000)  # B10: tilt + sparkle, never a shake
    sim(page, "t")
    page.locator("#cap", has_text="அடுத்த படம்").wait_for(timeout=10000)
    page.wait_for_function(f"() => document.querySelector('#picbtn img')?.getAttribute('src') !== '{first}'", timeout=15000)
    errs = [a for a in attempts(page.base)[:2] if a["verdict"] == "error_t"]
    assert len(errs) == 2


def test_english_gets_tamil_prompt_then_correct(page):
    start_practice(page)
    sim(page, "english")
    page.locator("#cap", has_text="தமிழ்ல சொல்லு").wait_for(timeout=5000)
    sim(page, "right")
    page.locator("#stars", has_text="1").wait_for(timeout=10000)


def test_parent_decides_when_two_voices(page):
    start_practice(page)
    sim(page, "two")
    page.locator(".parent-strip").wait_for(timeout=5000)
    assert "குழந்தை மட்டும் சொல்லட்டும்" in page.inner_text(".parent-strip")
    page.click(".parent-strip [data-v=correct]")
    page.locator("#stars", has_text="1").wait_for(timeout=10000)
    row = attempts(page.base)[0]
    assert row["decided_by"] == "parent" and row["verdict"] == "correct" and row["pesu_verdict"] == "unsure"


def test_noise_gate_pauses_before_listening(page):
    page.goto(f"/app/#/p/{KID}")
    page.click("#start")
    page.click("[data-sim=tv]")
    page.locator(".noise-box").wait_for(timeout=15000)
    page.click(".noise-box button")
    page.wait_for_selector(".stage[data-phase=listen]", timeout=15000)


def test_silent_child_gets_pause_screen(page):
    """A1: three words in a row with nothing scored -> 'still here?' instead of prompting an empty room."""
    start_practice(page)
    for _ in range(6):  # 2 silences per word x 3 words
        sim(page, "silence")
    page.locator(".overlay", has_text="இன்னும் இங்க இருக்காங்களா").wait_for(timeout=15000)
    page.click(".overlay [data-act=finish]")
    page.locator(".done-btn").wait_for(timeout=10000)


def test_exit_mid_try_stops_everything(page):
    """A4: after exit there is no scoring, no saving and no sound."""
    start_practice(page)
    page.hover("#exit")
    page.mouse.down()
    time.sleep(1.4)
    page.mouse.up()
    page.wait_for_url(f"**/#/p/{KID}", timeout=5000)
    n = len(page.requests)
    page.click("[data-sim=right]") if page.locator("[data-sim=right]").count() else None
    time.sleep(3)
    late = [u for u in page.requests[n:] if "/api/score" in u or "/api/attempts" in u]
    assert late == []
    speaking = page.evaluate("() => window.speechSynthesis.speaking")
    assert speaking is False


def test_stubbed_recogniser_path(page):
    """The real (non-Judge) path with a stubbed recogniser: confidences, t-error, raw transcript saved."""
    page.add_init_script("""
      window.webkitSpeechRecognition = class {
        start() { setTimeout(() => {
          const alt = (t, c) => ({ transcript: t, confidence: c });
          const res = [alt('டாக்கா', 0.82), alt('காக்கா', 0)];
          this.onresult && this.onresult({ results: [res] });
          this.onend && this.onend();
        }, 300); }
        stop() {} abort() {}
      };
      window.SpeechRecognition = window.webkitSpeechRecognition;""")
    start_practice(page)
    page.locator(".stage.tilt").wait_for(timeout=10000)
    row = attempts(page.base)[0]
    assert row["verdict"] == "error_t" and row["transcript"] == "டாக்கா" and abs(row["confidence"] - 0.82) < 1e-6


@pytest.mark.parametrize("page", ["server_nodemo"], indirect=True)
def test_record_only_when_recogniser_offline(page):
    """A2/B20: 'network' error -> kind parent message, then tries are saved as 'unscored'."""
    c = therapist_api(page.base)
    kid = c.post("/api/children", json={"name": "Nila", "age": 5}).json()["id"]
    page.add_init_script("""
      window.webkitSpeechRecognition = class {
        start() { setTimeout(() => { this.onerror && this.onerror({ error: 'network' }); this.onend && this.onend(); }, 200); }
        stop() {} abort() {}
      };
      window.SpeechRecognition = window.webkitSpeechRecognition;""")
    page.goto(f"/app/#/p/{kid}")
    page.click("#start")
    page.locator("#pmsg", has_text="No internet").wait_for(timeout=15000)
    page.locator("#cap", has_text="நல்லா முயற்சி").wait_for(timeout=30000)
    rows = c.get(f"/api/children/{kid}/attempts", params={"days": 1}).json()["attempts"]
    assert rows and all(r["verdict"] == "unscored" and r["decided_by"] == "none" for r in rows)
    assert rows[0]["has_audio"]


def test_therapist_override_in_ui(page):
    page.goto("/app/#/t")
    page.fill("#pin", "1234")
    page.click("#f button")
    page.locator("table.roster").wait_for()
    page.goto(f"/app/#/t/{KID}/review")
    row = page.locator("tbody tr[data-id]").first
    row.locator("[data-v=error_t]").click()
    page.locator("table.review .tag", has_text="therapist").first.wait_for(timeout=5000)
    assert "therapist: " in page.text_content("table.review")  # audit trail line (inside <details>)
