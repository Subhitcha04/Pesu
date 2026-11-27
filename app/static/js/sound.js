// Voice output and earcons (A9, A19, B6, B18).
// One shared AudioContext for every earcon; all effects <= 1.2 s, peak <= -6 dBFS (gain 0.5),
// and nothing ever plays during the listening window.
"use strict";
import { sleep } from "./util.js";

let ctx = null;
const PEAK = 0.5;                      // -6 dBFS
export const volume = { value: Number(localStorage.getItem("pesu-volume") ?? 0.8) };

export function setVolume(v) { volume.value = v; try { localStorage.setItem("pesu-volume", String(v)); } catch { /* storage may be blocked */ } }

export function audioCtx() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

function tone(freq, start, dur, type = "sine") {
  const c = audioCtx();
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.value = freq;
  o.connect(g); g.connect(c.destination);
  const t = c.currentTime + start, peak = PEAK * volume.value * 0.5;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.start(t); o.stop(t + dur + 0.02);
}

export const earcon = {
  yourTurn: () => { tone(523, 0, 0.18); tone(784, 0.16, 0.22); return sleep(400); },   // rising: your turn
  done: () => { tone(659, 0, 0.15); tone(440, 0.13, 0.2); return sleep(350); },        // falling: turn over
  success: () => { [660, 880, 1320].forEach((f, i) => tone(f, i * 0.11, 0.3)); return sleep(500); },
  sparkle: () => { [1200, 1500].forEach((f, i) => tone(f, i * 0.08, 0.15, "triangle")); return sleep(250); },
  test: () => earcon.yourTurn(),
};

let tamilVoice = null;
function pickVoice() {
  const voices = window.speechSynthesis?.getVoices() || [];
  tamilVoice = voices.find((v) => v.lang === "ta-IN") || voices.find((v) => v.lang?.startsWith("ta")) || null;
}
if ("speechSynthesis" in window) { pickVoice(); speechSynthesis.onvoiceschanged = pickVoice; }
export const hasTamilVoice = () => !!tamilVoice;

let currentAudio = null;

/** Speak Tamil text. A19: the safety timeout scales with text length and is cleared on end. */
export function speak(text) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !text) return resolve();
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ta-IN"; u.rate = 0.9; u.volume = volume.value;
    if (tamilVoice) u.voice = tamilVoice;
    const timer = setTimeout(resolve, 90 * text.length + 1500);   // pitfall: Android may never fire onend
    u.onend = u.onerror = () => { clearTimeout(timer); resolve(); };
    speechSynthesis.speak(u);
  });
}

export function playUrl(url) {
  return new Promise((resolve, reject) => {
    const a = new Audio(url);
    a.volume = volume.value;
    currentAudio = a;
    a.onended = () => { currentAudio = null; resolve(); };
    a.onerror = () => { currentAudio = null; reject(new Error("clip failed")); };
    a.play().catch((e) => { currentAudio = null; reject(e); });
  });
}

export function stopAllSound() {
  window.speechSynthesis?.cancel();
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
}
