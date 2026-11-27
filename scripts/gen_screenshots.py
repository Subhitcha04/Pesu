"""Generate the README screenshots deterministically (F24) into docs/screenshots/.

Starts its own server with demo data in a temp dir, drives the real UI with Playwright and
Judge Mode, and saves phone (390x844) and therapist (1280x800) screenshots.
Usage: python scripts/gen_screenshots.py   (PESU_E2E_CHROME=/path/to/chrome to use a system Chrome)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.e2e.conftest import FAST_TTS, SILENCE, start_server, therapist_api  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
KID = "kavin-sample"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    proc, base = start_server(Path(tempfile.mkdtemp()), demo=True)
    try:
        therapist_api(base).post(f"/api/children/{KID}/demo/fast-forward")
        with sync_playwright() as p:
            b = p.chromium.launch(
                executable_path=os.getenv("PESU_E2E_CHROME") or None,
                args=[
                    "--no-sandbox",
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-audio-capture={SILENCE}",
                ],
            )
            phone = b.new_context(viewport={"width": 390, "height": 844}, base_url=base, device_scale_factor=2)
            phone.add_init_script(FAST_TTS)
            # A silent recogniser stub: screenshots show Judge Mode, not headless-Chrome mic errors.
            phone.add_init_script("""window.webkitSpeechRecognition = window.SpeechRecognition = class {
                start() {} stop() { this.onend && this.onend(); } abort() { this.onend && this.onend(); } };""")
            phone.grant_permissions(["microphone"], origin=base)
            pg = phone.new_page()
            pg.goto("/app/#/")
            pg.wait_for_selector(".roles")
            pg.screenshot(path=OUT / "phone-home.png")
            pg.goto(f"/app/#/p/{KID}")
            pg.wait_for_selector(".ring")
            pg.screenshot(path=OUT / "parent-today.png")
            pg.click("#start")
            pg.wait_for_selector(".stage[data-phase=listen]", timeout=15000)
            pg.wait_for_timeout(600)
            pg.screenshot(path=OUT / "child-your-turn.png")
            pg.click("[data-sim=right]")
            pg.wait_for_selector(".stage.win", timeout=10000)
            pg.wait_for_timeout(250)
            pg.screenshot(path=OUT / "child-correct.png")
            pg.wait_for_selector(".stage[data-phase=listen]", timeout=15000)
            pg.click("[data-sim=two]")
            pg.wait_for_selector(".parent-strip", timeout=10000)
            pg.screenshot(path=OUT / "parent-decides.png")
            pg.click(".parent-strip [data-v=correct]")
            pg.goto(f"/app/#/p/{KID}/garden")
            pg.wait_for_selector(".garden")
            pg.screenshot(path=OUT / "sticker-garden.png")
            pg.goto(f"/app/#/p/{KID}/summary/today")
            pg.wait_for_selector(".summary-line")
            pg.screenshot(path=OUT / "parent-summary.png")

            desk = b.new_context(viewport={"width": 1280, "height": 800}, base_url=base)
            dp = desk.new_page()
            dp.goto("/app/#/t")
            dp.fill("#pin", "1234")
            dp.click("#f button")
            dp.wait_for_selector("table.roster")
            dp.screenshot(path=OUT / "therapist-roster.png")
            dp.goto(f"/app/#/t/{KID}")
            dp.wait_for_selector(".words")
            dp.screenshot(path=OUT / "therapist-setup.png")
            dp.goto(f"/app/#/t/{KID}/review?days=14")
            dp.wait_for_selector("table.review")
            dp.wait_for_timeout(300)
            dp.screenshot(path=OUT / "therapist-review.png")
            dp.goto(f"/app/#/t/{KID}/mic")
            dp.wait_for_selector("#sim")
            dp.click("#sim button")
            dp.wait_for_function("() => document.getElementById('out').textContent.includes('Verdict')")
            dp.screenshot(path=OUT / "therapist-mic-test.png")
            b.close()
    finally:
        proc.terminate()
    for f in sorted(OUT.glob("*.png")):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
