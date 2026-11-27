// Microphone, noise measurement and one listening turn (A2, A16/B8, A17, F13, F21).
"use strict";
import { audioCtx } from "./sound.js";
import { sleep } from "./util.js";

export const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition || null;

/** Judge Mode channel (F21): drawer buttons resolve the current listening turn with scripted
 * alternatives. It feeds exactly the same scoring path as the real recogniser. */
export const judge = {
  waiting: null, queued: null, tvOn: false,
  // A click while Pesu is still talking is queued for the next listening turn.
  feed(sim) { if (this.waiting) { this.waiting(sim); return true; } this.queued = sim; return false; },
};

export class Mic {
  constructor() { this.stream = null; this.source = null; this.analyser = null; this.shareable = true; }

  get ready() { return !!this.analyser; }

  async open() {
    if (this.stream && this.stream.active) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: false },
    });
    const c = audioCtx();
    this.source = c.createMediaStreamSource(this.stream);
    this.analyser = c.createAnalyser();
    this.analyser.fftSize = 1024;
    this.source.connect(this.analyser);
  }

  close() {
    this.stream?.getTracks().forEach((t) => t.stop());
    try { this.source?.disconnect(); } catch { /* already gone */ }
    this.stream = this.source = this.analyser = null;
  }

  rms() {
    if (!this.analyser) return 0;            // pitfall (A4): v0.1 threw here after close()
    const buf = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(buf);
    let s = 0;
    for (const x of buf) s += x * x;
    return Math.sqrt(s / buf.length);
  }

  /** Median room level over `ms` (>= 10 samples), so one door slam doesn't count. */
  async measure(ms = 600, onLevel) {
    if (judge.tvOn) { onLevel?.(0.2); await sleep(ms); return 0.2; }
    const levels = [];
    const end = performance.now() + ms;
    while (performance.now() < end || levels.length < 10) {
      const r = this.rms(); levels.push(r); onLevel?.(r);
      await sleep(Math.max(20, ms / 12));
    }
    levels.sort((a, b) => a - b);
    return levels[Math.floor(levels.length / 2)] || 0;
  }
}

/** B8: listening window by age, +2 s if the child was slow last time, capped at 8 s. */
export function listenWindow(age, lastLatencyMs, lastWindowMs) {
  const base = age <= 3 ? 6000 : age <= 5 ? 5000 : 4000;
  const slow = lastLatencyMs != null && lastWindowMs && lastLatencyMs > 0.7 * lastWindowMs;
  return Math.min(8000, base + (slow ? 2000 : 0));
}

// A2: what each recogniser error means for the parent, and whether to switch to record-only.
export const REC_ERRORS = {
  "network": { ta: "இணையம் இல்ல. Pesu பதிவு பண்ணும், therapist அப்புறம் கேப்பாங்க.",
    en: "No internet for speech recognition. Pesu will record and the therapist will listen later.", recordOnly: true },
  "service-not-allowed": { ta: "இந்த browser-ல பேச்சு அறிதல் இல்ல. Pesu பதிவு மட்டும் பண்ணும்.",
    en: "Speech recognition isn't allowed in this browser. Pesu will record only.", recordOnly: true },
  "language-not-supported": { ta: "தமிழ் அறிதல் இங்க இல்ல. Pesu பதிவு மட்டும் பண்ணும்.",
    en: "Tamil recognition isn't available here. Pesu will record only.", recordOnly: true },
  "not-allowed": { ta: "Mic அனுமதி இல்ல. Browser settings-ல mic-ஐ allow பண்ணுங்க.",
    en: "Microphone permission is off. Allow the mic in browser settings.", stop: true },
  "shared-mic": { ta: "இந்த phone-ல குரல் பதிவு சேமிக்க முடியல; பயிற்சி தொடரும்.",
    en: "Audio clips can't be saved on this phone; practice still works." },
};

/**
 * One listening turn. Recognition (unless record-only), recording, background level and
 * speech-onset detection all run together. Resolves to
 * {alternatives, confidences, audio, noise, latencyMs, error, simulated}.
 * session.stopListening() aborts it immediately (A4).
 */
export function listen(mic, { windowMs, background = 0, onLevel, session }) {
  const out = { alternatives: [], confidences: [], audio: null, noise: 0, latencyMs: null, error: null, simulated: false };
  const useRec = !!SpeechRec && !session.recordOnly && !session.judgeOnly;
  return new Promise((resolve) => {
    let finished = false, rec = null, recorder = null, endpointed = false;
    const chunks = [], frames = [];
    const t0 = performance.now();
    const onsetLevel = Math.max(background * 3, 0.02);
    let onsetAt = null, lastLoud = null;

    const finish = async () => {
      if (finished) return;
      finished = true;
      clearInterval(sampler); clearTimeout(timer);
      judge.waiting = null; session.stopListening = null;
      if (recorder && recorder.state === "recording") {
        await new Promise((r) => { recorder.onstop = r; recorder.stop(); });
        out.audio = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      }
      frames.sort((a, b) => a - b);
      if (out.forcedNoise == null) out.noise = frames.length ? frames[Math.floor(frames.length * 0.3)] : 0;
      else out.noise = out.forcedNoise;
      out.latencyMs = onsetAt ? Math.round(onsetAt - t0) : null;
      if (useRec && !mic.shareable && !mic.ready) await mic.open().catch(() => {});
      resolve(out);
    };

    session.stopListening = () => { try { rec?.abort(); } catch { /* not started */ } finish(); };
    judge.waiting = (sim) => {
      out.alternatives = sim.alternatives; out.confidences = sim.confidences || [];
      out.simulated = true;
      if (sim.noise != null) out.forcedNoise = sim.noise;
      onsetAt = onsetAt || performance.now();
      try { rec?.abort(); } catch { /* fine */ }
      finish();
    };

    // Pitfall: some Android Chrome builds refuse to share the mic between MediaRecorder and
    // SpeechRecognition (error 'audio-capture'). After the first failure we release the mic
    // while recognition runs, and stop saving clips on that phone.
    if (useRec && !mic.shareable) mic.close();
    if (mic.ready && window.MediaRecorder) {
      try {
        recorder = new MediaRecorder(mic.stream);
        recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
        recorder.start();
      } catch { recorder = null; }
    }

    const sampler = setInterval(() => {
      const r = mic.rms(); frames.push(r); onLevel?.(r);
      const now = performance.now();
      if (r > onsetLevel) { onsetAt = onsetAt || now; lastLoud = now; }
      else if (onsetAt && lastLoud && now - lastLoud > 1200 && !endpointed) {
        endpointed = true;                       // B8 endpointing: 1.2 s after speech ends
        if (rec) { try { rec.stop(); } catch { /* fine */ } } else finish();
      }
    }, 50);
    const timer = setTimeout(() => { if (rec) { try { rec.stop(); } catch { finish(); } } else finish(); }, windowMs);

    if (judge.queued) {               // a Judge Mode click made while Pesu was still talking
      const q = judge.queued; judge.queued = null;
      const feed = judge.waiting;
      setTimeout(() => feed(q), 250);   // feed() is a no-op if the turn already ended
      return;
    }
    if (useRec) {
      rec = new SpeechRec();
      rec.lang = "ta-IN"; rec.interimResults = false; rec.continuous = false; rec.maxAlternatives = 5;
      rec.onresult = (e) => {
        const r = Array.from(e.results[0] || []);
        out.alternatives = r.map((a) => a.transcript);
        out.confidences = r.map((a) => a.confidence || 0);   // A17
      };
      rec.onerror = (e) => {
        if (e.error === "no-speech" || e.error === "aborted") return;     // silence is not an error
        if (e.error === "audio-capture" && mic.shareable) { mic.shareable = false; out.error = "shared-mic"; return; }
        out.error = e.error;
      };
      rec.onend = () => finish();
      try { rec.start(); } catch { out.error = "service-not-allowed"; finish(); }
    }
  });
}
