"""E2E fixtures (F16): a real uvicorn server per module + Chromium via Playwright.

Why stubs: headless Chrome's real recogniser needs Google's servers and is flaky, so tests either
use Judge Mode (the same code path the drawer uses) or stub window.webkitSpeechRecognition.
Browser: PESU_E2E_CHROME=/path/to/chrome, otherwise Playwright's bundled Chromium
(`python -m playwright install chromium`).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SILENCE = Path(__file__).with_name("silence.wav")
# Make speech synthesis instant so tests don't wait for (possibly missing) Tamil voices.
FAST_TTS = "window.speechSynthesis && (window.speechSynthesis.speak = (u) => setTimeout(() => u.onend && u.onend(), 20));"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(tmp: Path, demo: bool) -> tuple[subprocess.Popen, str]:
    port = free_port()
    env = {**os.environ, "PESU_DATA_DIR": str(tmp), "PESU_DEMO": "1" if demo else "0"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/api/health").status_code == 200:
                return proc, base
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("server did not start")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc, base = start_server(tmp_path_factory.mktemp("e2e"), demo=True)
    yield base
    proc.terminate()


@pytest.fixture(scope="module")
def server_nodemo(tmp_path_factory):
    proc, base = start_server(tmp_path_factory.mktemp("e2e-nodemo"), demo=False)
    yield base
    proc.terminate()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        exe = os.getenv("PESU_E2E_CHROME")
        b = p.chromium.launch(
            executable_path=exe or None,
            args=[
                "--no-sandbox",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={SILENCE}",
            ],
        )
        yield b
        b.close()


@pytest.fixture()
def page(browser, request):
    base = request.getfixturevalue(request.param if hasattr(request, "param") else "server")
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, base_url=base)
    ctx.grant_permissions(["microphone"], origin=base)
    ctx.add_init_script(FAST_TTS)
    pg = ctx.new_page()
    pg.base = base
    pg.errors, pg.requests = [], []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("request", lambda r: pg.requests.append(r.url))
    yield pg
    external = [u for u in pg.requests if not u.startswith(base) and not u.startswith("blob:") and not u.startswith("data:")]
    ctx.close()
    assert not external, f"unexpected outbound requests: {external}"  # B22 / acceptance criterion
    assert not pg.errors, pg.errors


def therapist_api(base: str) -> httpx.Client:
    c = httpx.Client(base_url=base)
    assert c.post("/api/pin", json={"pin": "1234"}).json()["ok"]
    return c
