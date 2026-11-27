// The child's practice screen: the voice flow (B1-B13, B19-B23), with session caps (A1),
// recogniser error handling (A2), clean exit (A4), back/refresh guard (A18) and Judge Mode (F21).
"use strict";
import { Mic, REC_ERRORS, SpeechRec, judge, listen, listenWindow } from "./mic.js";
import { earcon, playUrl, speak, stopAllSound } from "./sound.js";
import { api, esc, on, picture, send, sleep, state, wordById } from "./util.js";

const MAX_PROMPTS = 12;                     // A1: hard cap on prompts per session
const MAX_MS = 6 * 60 * 1000;               // A1: 6 minutes wall clock
const MAX_IDLE_WORDS = 3;                   // A1: 3 words in a row with nothing scored -> pause screen
const RESUME_MS = 6 * 60 * 1000;

class SessionAborted extends Error {}

export async function viewPractice(view, childId, navigate) {
  const kid = await api(`/api/children/${childId}/practice`);
  const demo = state.config.demo;
  document.body.classList.add("child");
  view.innerHTML = `
    <div class="practice" id="pr">
      <div class="parent-msg hidden" id="pmsg" role="status"></div>
      <button class="exit" id="exit" aria-label="Parent: hold to leave practice">
        <svg viewBox="0 0 36 36" class="exit-ring"><circle cx="18" cy="18" r="15"/></svg>
        <span>பெற்றோர்: அழுத்தி பிடிங்க<span class="en">Parent: hold to exit</span></span>
      </button>
      <div class="stage" id="stage">
        <svg class="count" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="46"/></svg>
        <button class="pic-btn" id="picbtn" aria-label="Hear it again"></button>
        <div class="sparkle" aria-hidden="true">✦</div>
        <div class="mic-ico" aria-hidden="true">🎙️</div>
      </div>
      <div class="caption" id="cap" aria-live="polite"></div>
      <div class="jar" id="jar"><img src="img/jar.svg" alt=""> <b id="stars">0</b></div>
      ${demo ? judgeDrawer() : ""}
    </div>`;

  const $ = (id) => document.getElementById(id);
  const $stage = $("stage"), $pic = $("picbtn"), $cap = $("cap"), $pr = $("pr");
  const caption = (ta, en) => { $cap.innerHTML = ta ? `<span lang="ta">${esc(ta)}</span>${en ? `<span class="en" lang="en">${esc(en)}</span>` : ""}` : ""; };
  const phase = (p) => { $stage.dataset.phase = p; };    // pesu | listen | think | idle (B6)

  // ---- session state (A4: one object owns everything that can outlive the screen)
  const mic = new Mic();
  const S = { stopped: false, recordOnly: !SpeechRec && !demo, judgeOnly: !SpeechRec && demo, stopListening: null, wakeLock: null };
  const alive = () => { if (S.stopped) throw new SessionAborted(); };
  const guard = async (p) => { const v = await p; alive(); return v; };

  // A18: resume after an accidental refresh
  const key = `pesu-session-${childId}`;
  let saved = 0, stars = 0, prompts = 0, wordIndex = 0, sessionId = null, startedAt = Date.now();
  try {
    const prev = JSON.parse(sessionStorage.getItem(key) || "null");
    if (prev && Date.now() - prev.startedAt < RESUME_MS) ({ saved, stars, prompts, wordIndex, sessionId, startedAt } = prev);
  } catch { /* corrupted: start fresh */ }
  const persist = () => sessionStorage.setItem(key, JSON.stringify({ saved, stars, prompts, wordIndex, sessionId, startedAt }));
  $("stars").textContent = stars;

  async function stop(reason, goTo) {
    if (S.stopped) return;
    S.stopped = true;
    judge.queued = null; judge.waiting = null; judge.tvOn = false;
    try { S.stopListening?.(); } catch { /* fine */ }
    stopAllSound();
    mic.close();
    S.wakeLock?.release?.().catch(() => {});
    window.removeEventListener("popstate", onBack);
    sessionStorage.removeItem(key);
    if (sessionId && reason) send(`/api/sessions/${sessionId}`, { end_reason: reason, stars }, "PATCH").catch(() => {});
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (goTo) navigate(goTo);
  }
  view.cleanup = () => stop("exit");

  // ---- B3: hold-to-exit with a visible filling ring (1.2 s)
  const exitBtn = $("exit");
  let holdTimer = null;
  const holdStart = (e) => { e.preventDefault(); exitBtn.classList.add("holding"); holdTimer = setTimeout(() => stop("exit", `#/p/${childId}`), 1200); };
  const holdEnd = () => { exitBtn.classList.remove("holding"); clearTimeout(holdTimer); };
  exitBtn.addEventListener("pointerdown", holdStart);
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => exitBtn.addEventListener(ev, holdEnd));

  // ---- A18: Android Back button opens a confirm instead of leaving
  history.pushState({ pesuGuard: true }, "");
  function onBack() {
    if (S.stopped) return;
    history.pushState({ pesuGuard: true }, "");
    if ($pr.querySelector(".back-confirm")) return;
    const box = document.createElement("div");
    box.className = "overlay back-confirm";
    box.innerHTML = `<b>பயிற்சியை விட்டு போகணுமா?</b><span class="en">Parent: leave practice?</span>
      <div class="row"><button class="big" data-act="stay">இல்ல · Stay</button><button class="big primary" data-act="leave">ஆமா · Leave</button></div>`;
    $pr.appendChild(box);
    on(box, "click", "button", (_, b) => { box.remove(); if (b.dataset.act === "leave") stop("exit", `#/p/${childId}`); });
  }
  window.addEventListener("popstate", onBack);

  // ---- B2: touch-safe shell
  $pr.addEventListener("contextmenu", (e) => e.preventDefault());
  try { S.wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* not supported: fine */ }

  // ---- parent-facing messages (A2, C12): written + spoken once
  async function parentMessage(code) {
    const m = REC_ERRORS[code];
    if (!m) return;
    const box = $("pmsg");
    box.innerHTML = `${esc(m.ta)}<span class="en">${esc(m.en)}</span>`;
    box.classList.remove("hidden");
    if (m.recordOnly) S.recordOnly = true;
    await guard(speak(m.ta));
  }

  function showNote(text) {
    const box = $("pmsg"); box.textContent = text; box.classList.remove("hidden");
  }

  // ---- voice helpers
  const words = kid.word_ids.map(wordById);
  const has = (w, kind) => kid.coverage.have.includes(`${w.id}:${kind}`);
  async function sayClip(w, kind) {
    if (has(w, kind)) {
      try { await guard(playUrl(`/api/children/${childId}/clips/${w.id}/${kind}`)); return true; }
      catch (e) { if (e instanceof SessionAborted) throw e; }
    }
    // B19: TTS may stand in for prompts; the model cue for the target sound must be the
    // therapist's recording (ta-IN TTS may not produce the contrast) - except in demo mode.
    if (kind === "cue" && !demo) return false;
    await guard(speak(w[kind]));
    return true;
  }

  let lastPraise = -1;
  const praisedWords = new Set();
  function praiseLine(w) {
    if (!praisedWords.has(w.id)) { praisedWords.add(w.id); return { ta: "நல்ல க சத்தம்!", en: "Good k sound!" }; }   // B12: name the sound
    let i;
    do { i = Math.floor(Math.random() * state.config.praise.length); } while (i === lastPraise && state.config.praise.length > 1);
    lastPraise = i;
    return state.config.praise[i];
  }

  async function celebrate(w) {
    stars += 1; $("stars").textContent = stars; persist();
    $stage.classList.add("win");
    const line = praiseLine(w);
    caption(line.ta, line.en);
    await guard(Promise.all([earcon.success(), sleep(150).then(() => speak(line.ta))]));
    await guard(sleep(300));
    $stage.classList.remove("win");
  }

  // ---- B11 success-rate guard + re-queue (B10)
  let nonCorrectRun = 0, idleWords = 0;
  const requeue = [];
  function bestWord() {
    const ws = kid.word_success;
    return [...words].sort((a, b) => {
      const ra = ws[a.id] ? ws[a.id].correct / Math.max(1, ws[a.id].scored) : 0;
      const rb = ws[b.id] ? ws[b.id].correct / Math.max(1, ws[b.id].scored) : 0;
      return rb - ra;
    })[0];
  }
  function nextWord() {
    if (nonCorrectRun >= 2) { nonCorrectRun = 0; return bestWord(); }   // guaranteed win
    if (requeue.length && saved >= Math.max(1, kid.tries_per_session - 3)) return requeue.shift();
    return words[wordIndex++ % words.length];
  }

  // ---- noise gate (before listening)
  async function waitForQuiet() {
    if (!mic.ready && !judge.tvOn) return 0;
    for (;;) {
      const level = await guard(mic.measure(600));
      if (level < state.config.noise_threshold) return level;
      const box = document.createElement("div");
      box.className = "overlay noise-box";
      box.innerHTML = `<b>கொஞ்சம் சத்தமா இருக்கு. TV-ய கம்மி பண்ணலாமா?</b>
        <span class="en">It's a bit noisy. Can you turn the TV down?</span>
        <div class="meter"><i></i></div><button class="primary big">Ready</button>`;
      $pr.appendChild(box);
      speak("கொஞ்சம் சத்தமா இருக்கு. டீவிய கம்மி பண்ணலாமா?");
      let live = true;
      (async () => { while (live && !S.stopped) { setMeter(box.querySelector(".meter"), judge.tvOn ? 0.2 : mic.rms()); await sleep(80); } })();
      await guard(new Promise((r) => (box.querySelector("button").onclick = () => { judge.tvOn = false; r(); })));
      live = false; box.remove();
    }
  }

  // ---- parent decides (C4): judge against a reference, not memory
  function askParent(w, hint, clip) {
    return new Promise((resolve, reject) => {
      const strip = document.createElement("div");
      strip.className = "parent-strip";
      strip.innerHTML = `${hint ? `<div class="muted">${esc(hint[0])}<span class="en">${esc(hint[1])}</span></div>` : ""}
        <b>க மாதிரி இருந்துச்சா?</b><span class="en">Parent: did it sound like க (k)?</span>
        <div class="row helpers">
          ${has(w, "cue") || demo ? '<button data-act="ref">▶ சரியான சத்தம் · Hear the right sound</button>' : ""}
          ${clip ? `<button data-act="replay">▶ ${esc(kid.name)} சொன்னது · Replay</button>` : ""}
        </div>
        <div class="row"><button class="verdict-btn" data-v="correct" aria-label="Yes, k">✓</button>
          <button class="verdict-btn" data-v="error_t" aria-label="No, t">✗</button>
          <button class="verdict-btn small" data-v="unsure">தெரியல<span class="en">Not sure</span></button></div>`;
      $pr.appendChild(strip);
      const url = clip ? URL.createObjectURL(clip) : null;
      on(strip, "click", "button", (_, b) => {
        if (S.stopped) { strip.remove(); return reject(new SessionAborted()); }
        if (b.dataset.act === "ref") return sayClip(w, "cue").catch(() => {});
        if (b.dataset.act === "replay") return playUrl(url).catch(() => {});
        strip.remove(); if (url) URL.revokeObjectURL(url); resolve(b.dataset.v);
      });
    });
  }

  async function saveTry(w, s, verdict, decidedBy, heard) {
    alive();
    const fd = new FormData();
    const fields = {
      child_id: childId, word_id: w.id, session_id: sessionId,
      pesu_verdict: s ? (s.verdict === "retry" ? "unsure" : s.verdict) : "unscored",
      verdict, decided_by: decidedBy, reason: s ? s.reason : "record_only",
      transcript: s ? s.heard : "", alternatives: JSON.stringify(heard.alternatives || []),
      noise_rms: heard.noise || 0,
    };
    if (s?.confidence != null) fields.confidence = s.confidence;
    if (heard.latencyMs != null) fields.latency_ms = heard.latencyMs;
    Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
    if (heard.audio && heard.audio.size > 400) fd.append("audio", heard.audio, "try.webm");   // skip header-only blobs
    await guard(api("/api/attempts", { method: "POST", body: fd }));
    saved += 1; persist();
  }

  // ---- one listening turn: earcons, countdown ring, thinking (B6, B7, B8)
  let lastLatency = null, lastWindow = null;
  async function turn(w) {
    const background = await waitForQuiet();
    const windowMs = listenWindow(kid.age, lastLatency, lastWindow);
    phase("listen");
    $stage.style.setProperty("--window", `${windowMs}ms`);
    caption("", "");
    await guard(earcon.yourTurn());
    const heard = await guard(listen(mic, { windowMs, background, session: S }));
    lastLatency = heard.latencyMs; lastWindow = windowMs;
    phase("think");
    earcon.done();
    if (heard.error && !heard.simulated) {
      if (demo && heard.error !== "shared-mic") {
        // Judge Mode: a missing/blocked recogniser must not end the demo; the drawer drives it.
        S.judgeOnly = true;
        showNote("Speech recognition unavailable here (" + heard.error + "). Use the Judge Mode buttons.");
      } else {
        await parentMessage(heard.error);
        if (REC_ERRORS[heard.error]?.stop) { await stop("exit", `#/p/${childId}`); throw new SessionAborted(); }
      }
    }
    return heard;
  }

  // ---- one word: prompt, up to two scored tries, retries for silence/English (B10)
  async function practiseWord(w, firstTime) {
    $pic.innerHTML = picture(w, "picture");
    phase("pesu");
    if (firstTime && kid.listen_first && has(w, "cue")) {          // B9 listen first
      caption(w.tamil, `Listen: ${w.latin} (${w.english[0]})`);
      for (let i = 0; i < 3; i++) { $stage.classList.add("bounce"); await sayClip(w, "cue"); $stage.classList.remove("bounce"); await guard(sleep(250)); }
    }
    caption(w.prompt, `Say ${w.latin} (${w.english[0]})!`);
    prompts += 1; persist();
    await sayClip(w, "prompt");
    let misses = 0, relistens = 0, scoredHere = 0;

    while (saved < kid.tries_per_session) {
      alive();
      const heard = await turn(w);

      if (heard.error && S.recordOnly && !heard.simulated && heard.error !== "shared-mic" && !S.recordOnlyStarted) {
        S.recordOnlyStarted = true;                               // the recogniser died mid-turn: that
        continue;                                                 // clip is cut short, so listen again
      }
      if (S.recordOnly && !heard.simulated) {                     // B20: record, don't judge
        if (!heard.audio && !heard.latencyMs) { if (relistens++ < 1) { caption("கேக்கல... சத்தமா சொல்லு!", "Didn't hear… say it loudly!"); await guard(speak("கேக்கல... சத்தமா சொல்லு!")); continue; } break; }
        await saveTry(w, null, "unscored", "none", heard); scoredHere++;
        caption("நல்லா முயற்சி பண்ண!", "Good try!"); await guard(speak("நல்லா முயற்சி பண்ண!"));
        break;
      }

      const s = await guard(send("/api/score", { word_id: w.id, alternatives: heard.alternatives,
        confidences: heard.confidences, noise_rms: heard.noise }));
      phase("pesu");

      if (s.reason === "correct") {
        await saveTry(w, s, "correct", "pesu", heard); scoredHere++;
        nonCorrectRun = 0; await celebrate(w); break;
      }
      if (s.reason === "error_t") {
        await saveTry(w, s, "error_t", "pesu", heard); scoredHere++;
        misses += 1; nonCorrectRun += 1;
        $stage.classList.add("tilt"); earcon.sparkle(); setTimeout(() => $stage.classList.remove("tilt"), 700);
        if (misses >= 2 || saved >= kid.tries_per_session) {
          await sayClip(w, "cue");
          caption("அடுத்த படம்!", "Next picture!"); await guard(speak("அடுத்த படம்!"));
          if (!requeue.includes(w) && misses >= 2) requeue.push(w);
          break;
        }
        caption(s.say_ta, s.say_en); await guard(speak(s.say_ta));
        caption(w.cue, "Copy the sound"); await sayClip(w, "cue");
        continue;
      }
      if ((s.reason === "silence" || s.reason === "english") && relistens < 1) {
        relistens += 1; caption(s.say_ta, s.say_en); await guard(speak(s.say_ta)); continue;
      }
      if (s.reason === "silence") break;                          // skipped, not counted

      const hint = s.reason === "multi" ? [s.say_ta, "Let only the child say it"]
        : s.reason === "noise" ? ["சத்தம் அதிகமா இருந்தது", "It got noisy while listening"] : null;
      caption("", "");
      const v = await guard(askParent(w, hint, heard.audio));
      await saveTry(w, s, v, "parent", heard); scoredHere++;
      if (v === "correct") { nonCorrectRun = 0; await celebrate(w); break; }
      nonCorrectRun += 1; misses += 1;
      if (misses >= 2 || v === "unsure") break;
      caption(w.cue, "Copy the sound"); await sayClip(w, "cue");
    }
    return scoredHere;
  }

  // ---- A1 pause screen
  function pauseScreen() {
    return new Promise((resolve) => {
      const box = document.createElement("div");
      box.className = "overlay";
      box.innerHTML = `<b>${esc(kid.name)} இன்னும் இங்க இருக்காங்களா?</b><span class="en">Is ${esc(kid.name)} still here?</span>
        <div class="col"><button class="big primary" data-act="continue">தொடரலாம் · Continue</button>
        <button class="big" data-act="finish">இன்னைக்கு போதும் · Finish for today</button></div>`;
      $pr.appendChild(box);
      speak(`${kid.name} இன்னும் இங்க இருக்காங்களா?`);
      on(box, "click", "button", (_, b) => { box.remove(); resolve(b.dataset.act); });
    });
  }

  // ---- picture tap = hear it again (B1), debounced for toddler slaps (B2)
  let lastTap = 0, currentWord = null;
  $pic.addEventListener("click", () => {
    const now = Date.now();
    if (now - lastTap < 800 || $stage.dataset.phase === "listen" || !currentWord) return;
    lastTap = now;
    sayClip(currentWord, "prompt").catch(() => {});
  });

  // ---- Judge Mode drawer (F21)
  if (demo) {
    on($pr, "click", "[data-sim]", (_, b) => {
      const w = currentWord; if (!w) return;
      const t = "ட" + w.tamil.slice(1);
      const sims = {
        right: { alternatives: [w.tamil], confidences: [0.9] },
        t: { alternatives: [t, w.tamil], confidences: [0.8, 0] },
        english: { alternatives: [w.english[0]], confidences: [0.9] },
        silence: { alternatives: [] },
        noisy: { alternatives: [w.tamil], confidences: [0.7], noise: 0.2 },
        two: { alternatives: [`${w.tamil} சொல்லு`], confidences: [0.8] },
        unclear: { alternatives: ["பாப்பா"], confidences: [0.6] },
      };
      if (b.dataset.sim === "tv") { judge.tvOn = true; b.classList.add("on"); return; }
      if (!judge.feed(sims[b.dataset.sim])) { b.classList.add("nudge"); setTimeout(() => b.classList.remove("nudge"), 600); }
    });
  }

  // ---- main loop
  try {
    try { await mic.open(); }
    catch {
      if (!demo) { await parentMessage("not-allowed"); return stop(null, `#/p/${childId}`); }
    }
    if (!SpeechRec && !demo) await parentMessage("service-not-allowed");
    if (!sessionId) { sessionId = (await guard(send("/api/sessions", { child_id: childId }))).id; persist(); }

    let endReason = "goal";
    const seen = new Set();
    while (saved < kid.tries_per_session) {
      alive();
      if (Date.now() - startedAt > MAX_MS) { endReason = "time_cap"; break; }
      if (prompts >= MAX_PROMPTS) { endReason = "prompt_cap"; break; }
      if (idleWords >= MAX_IDLE_WORDS) {
        const act = await guard(pauseScreen());
        idleWords = 0;
        if (act === "finish") { endReason = saved ? "finished" : "silence"; break; }
      }
      const w = nextWord();
      currentWord = w;
      const scored = await practiseWord(w, !seen.has(w.id));
      seen.add(w.id);
      idleWords = scored ? 0 : idleWords + 1;
      await guard(sleep(350));
    }
    // ---- end of session: sticker (B13), sleepy goodbye (B23)
    phase("idle");
    const end = await guard(send(`/api/sessions/${sessionId}`, { end_reason: endReason, stars }, "PATCH"));
    sessionStorage.removeItem(key);
    const sid = sessionId; sessionId = null;          // already ended: stop() must not end it again
    $stage.innerHTML = end.sticker_id
      ? `<img class="picture sticker-new" src="img/stickers/${end.sticker_id}.svg" alt="New sticker">`
      : `<img class="picture" src="img/jar.svg" alt="">`;
    const line = `சூப்பர்! இன்னைக்கு ${stars} நட்சத்திரம்`;
    caption(line, end.sticker_id ? `Super! ${stars} stars and a new sticker` : `Super! ${stars} stars today`);
    await guard(Promise.all([earcon.success(), speak(line)]));
    const done = document.createElement("button");
    done.className = "primary big done-btn"; done.innerHTML = "முடிஞ்சது<span class='en'>Done</span>";
    done.onclick = () => stop(null, `#/p/${childId}/summary/${sid}?from=done`);
    $cap.after(done);
    mic.close();
  } catch (e) {
    if (!(e instanceof SessionAborted)) throw e;
  }
}

function judgeDrawer() {
  return `<details class="judge" open>
    <summary>Judge Mode · Simulate the child</summary>
    <p class="en">Feeds the same scoring path as the microphone. Shown only when PESU_DEMO=1.</p>
    <div class="sims">
      <button data-sim="right">✓ Says it right</button>
      <button data-sim="t">Says the t-version</button>
      <button data-sim="english">Says the English word</button>
      <button data-sim="silence">Silence</button>
      <button data-sim="two">Parent speaks along</button>
      <button data-sim="noisy">Noisy while listening</button>
      <button data-sim="unclear">Unclear word</button>
      <button data-sim="tv">TV on (before listening)</button>
    </div></details>`;
}

export function setMeter(el, r) {
  if (!el) return;
  el.querySelector("i").style.width = Math.min(100, (r / 0.25) * 100) + "%";
  el.classList.toggle("loud", r >= state.config.noise_threshold);
}
