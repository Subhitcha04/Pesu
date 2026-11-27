// Parent screens: pick child, today, summary, sticker garden, privacy (C2, C4-C5, C9-C10, B13, B18, B23).
"use strict";
import { Mic } from "./mic.js";
import { setMeter } from "./practice.js";
import { earcon, playUrl, setVolume, speak, volume } from "./sound.js";
import { api, esc, fmtDayOnly, on, picture, state, taNum, wordById, wordLabel } from "./util.js";

const VERDICT = { correct: "✓ சரி · right", error_t: "✗ 't' · heard t", unsure: "? தெரியல · not sure", unscored: "◌ therapist கேப்பாங்க · therapist will listen" };

export async function viewPickChild(view) {
  const kids = await api("/api/children");
  view.innerHTML = `
    <a class="back" href="#/">← Home</a>
    <h1>உங்க குழந்தை<span class="en">Your child</span></h1>
    <div class="chips">${kids.map((k) => `
      <a class="chip" href="#/p/${k.id}"><span class="avatar">${esc(k.name[0] || "?")}</span>
        <b>${esc(k.name)}</b><span class="muted">${k.age} yrs</span></a>`).join("") || '<p class="muted">No children yet. The therapist adds them.</p>'}
    </div>`;
}

function ring(done, goal) {
  const r = 62, c = 2 * Math.PI * r, frac = Math.min(1, goal ? done / goal : 0);
  return `<svg class="ring" viewBox="0 0 150 150" role="img" aria-label="${done} of ${goal} tries today">
    <circle cx="75" cy="75" r="${r}" fill="none" stroke="#f1e3c4" stroke-width="14"/>
    ${frac > 0 ? `<circle cx="75" cy="75" r="${r}" fill="none" stroke="#0f766e" stroke-width="14" stroke-linecap="round"
      stroke-dasharray="${c * frac} ${c}" transform="rotate(-90 75 75)"/>` : ""}
    <text x="75" y="84" text-anchor="middle" font-size="28" font-weight="800" fill="#1f2a2e">${done}/${goal}</text></svg>`;
}

export async function viewToday(view, id, navigate) {
  const kid = await api(`/api/children/${id}/practice`);
  const practised = kid.week.filter((d) => d.practised).length;
  const enough = kid.today.sessions >= kid.sessions_per_day;
  const last = kid.last_session;
  view.innerHTML = `
    <a class="back" href="#/p">← Back</a>
    <h1>${esc(kid.name)}<span class="en">Today</span></h1>
    <div class="row today">
      ${ring(kid.today.tries, kid.today.goal)}
      <div>
        <b>இந்த வாரம் ${practised}/7 நாள்</b><span class="en">Days practised this week (rest days are fine)</span>
        <div class="week">${kid.week.map((d) => `<span class="dot ${d.practised ? "on" : ""}" title="${fmtDayOnly(d.day)}">${fmtDayOnly(d.day).slice(0, 2)}</span>`).join("")}</div>
        ${last ? `<p class="muted">Last session: ${last.stars} ⭐${last.sticker_id ? " + a sticker" : ""}</p>` : ""}
      </div>
    </div>
    ${kid.parent_note ? `<p class="quote">“${esc(kid.parent_note)}”<span class="en">Therapist's note</span></p>` : ""}
    ${enough ? `<div class="sleepy"><img src="img/sleepy.svg" alt=""><b>இன்னைக்கு போதும்! நாளைக்கு பாக்கலாம்</b>
        <span class="en">That's enough for today. See you tomorrow!</span></div>
        <button class="big" id="start">பெற்றோர்: மறுபடியும் பயிற்சி<span class="en">Parent: practise again anyway</span></button>`
      : `<button class="primary huge" id="start">பயிற்சி ஸ்டார்ட் பண்ணலாம்<span class="en">Let's start practice</span></button>`}
    <div class="row links">
      <a class="btn" href="#/p/${id}/summary/today">இன்னைக்கு summary · Today&#39;s summary</a>
      <a class="btn" href="#/p/${id}/garden">🌼 தோட்டம் · Sticker garden (${kid.stickers.length})</a>
      <a class="btn" href="#/privacy">தனியுரிமை · Privacy</a>
    </div>
    <details class="card"><summary>Before you start: mic + sound check</summary>
      <p>Say "hello". The bar should move. Then stay quiet: Pesu needs the room below the line.</p>
      <div class="meter" id="meter"><i></i></div><p id="room" class="muted"></p>
      <div class="row"><button id="mictest">🎙️ Test mic (3 s)</button><button id="eartest">🔔 Test sounds</button>
        <label>Volume <input type="range" id="vol" min="0" max="1" step="0.05" value="${volume.value}"></label></div>
      <p class="muted">Tips: phone at the child's eye level · let the child answer alone · stay silent while the ring is green · 5 minutes beats 30.</p>
    </details>`;
  document.getElementById("start").onclick = () => {
    document.documentElement.requestFullscreen?.().catch(() => {});   // must happen inside the tap (B2)
    navigate(`#/p/${id}/practice`);
  };
  document.getElementById("vol").oninput = (e) => setVolume(Number(e.target.value));
  document.getElementById("eartest").onclick = () => earcon.test();
  document.getElementById("mictest").onclick = async () => {
    const mic = new Mic();
    const room = document.getElementById("room");
    try { await mic.open(); } catch { room.textContent = "Mic blocked. Allow it in the browser and try again."; return; }
    const levels = [];
    await mic.measure(3000, (r) => { levels.push(r); setMeter(document.getElementById("meter"), r); });
    mic.close();
    levels.sort((a, b) => a - b);
    const quiet = levels[Math.floor(levels.length * 0.2)], loud = levels[levels.length - 1];
    const t = state.config.noise_threshold;
    room.textContent = `${loud > 0.03 ? "Mic works ✓" : "Didn't hear anything: check the mic."} Room: ${
      quiet < t * 0.5 ? "quiet ✓" : quiet < t ? "a bit noisy" : "too noisy for practice"}`;
  };
}

export function summarySentence(s) {
  // A10/C5: built from the data; denominator = scored tries only; spoken with Tamil number words.
  const when = s.scope === "today" ? "இன்னைக்கு" : "அன்னைக்கு";
  const shown = `${when} ${s.sound} சத்தம் ${s.scored}-ல ${s.correct} சரி.`;
  const spoken = `${when} ${s.sound} சத்தம் ${taNum(s.scored)}ல ${taNum(s.correct)} சரி.`;
  const extra = [];
  if (s.parent_decided) extra.push(`${s.parent_decided} வார்த்தை உங்க முடிவு.`);
  if (s.unscored) extra.push(`${s.unscored} முயற்சி therapist கேப்பாங்க.`);
  return { shown: [shown, ...extra].join(" "), spoken: [spoken, ...extra].join(" ") };
}

export async function viewSummary(view, id, sid, query) {
  const kid = await api(`/api/children/${id}/practice`);
  const s = await api(`/api/children/${id}/summary${sid === "today" ? "" : `?session_id=${encodeURIComponent(sid)}`}`);
  const line = summarySentence(s);
  view.innerHTML = `
    <a class="back" href="#/p/${id}">← Today</a>
    <h1>${esc(kid.name)} · சுருக்கம்<span class="en">Summary</span></h1>
    <div class="card"><div class="row"><button id="say" aria-label="Read aloud">▶</button>
      <b class="summary-line" lang="ta">${esc(line.shown)}</b></div>
      <span class="en">${s.scope === "today" ? "Today" : "That day"}: ${s.correct} of ${s.scored} k sounds right${s.parent_decided ? `, ${s.parent_decided} decided by you` : ""}${s.unscored ? `, ${s.unscored} for the therapist to hear` : ""}.</span></div>
    <table><tbody>${s.items.map((a) => {
      const w = wordById(a.word_id);
      return `<tr><td>${picture(w, "thumb")} ${wordLabel(w)}</td><td><span class="verdict v-${a.verdict}">${VERDICT[a.verdict]}</span>
        ${a.decided_by === "parent" ? '<span class="tag">நீங்க · you</span>' : ""}</td>
        <td>${a.has_audio ? `<button data-play="${a.id}" aria-label="Play">▶</button>` : ""}</td></tr>`;
    }).join("") || '<tr><td class="muted">No tries yet.</td></tr>'}</tbody></table>`;
  document.getElementById("say").onclick = () => speak(line.spoken);
  on(view, "click", "[data-play]", (_, b) => playUrl(`/api/attempts/${b.dataset.play}/audio`).catch(() => {}));
  if (query.get("from") === "done") speak(line.spoken);    // arrived by a tap, so autoplay is allowed
}

export async function viewGarden(view, id) {
  const kid = await api(`/api/children/${id}/practice`);
  const owned = new Set(kid.stickers);
  view.innerHTML = `
    <a class="back" href="#/p/${id}">← Today</a>
    <h1>🌼 ${esc(kid.name)}-ஓட தோட்டம்<span class="en">Sticker garden: one new sticker for each finished session. Stickers are never taken away.</span></h1>
    <div class="garden">${state.config.stickers.map((s) => owned.has(s)
      ? `<img src="img/stickers/${s}.svg" alt="${s}">`
      : `<div class="slot" aria-label="not yet"></div>`).join("")}</div>`;
}

export function viewPrivacy(view) {
  view.innerHTML = `
    <a class="back" href="#/">← Home</a>
    <h1>Privacy · தனியுரிமை</h1>
    <div class="card prose">
      <p><b>What Pesu records:</b> each practice try (the word, Pesu's verdict, your verdict if asked, the therapist's verdict) and a short audio clip of your child saying the word.</p>
      <p><b>Where it is stored:</b> only on the computer that runs Pesu (its data folder). There are no accounts, no ads and no analytics.</p>
      <p><b>What leaves this device:</b> in Chrome, speech recognition sends the microphone audio of each try to Google's speech service to get the text. Pesu itself sends nothing anywhere else. If the internet is off, Pesu records the tries for the therapist instead.</p>
      <p><b>Delete or take your data:</b> ask the therapist to use <i>Export</i> (a ZIP with all tries and audio) or <i>Delete child</i> (removes every row and audio file) on your child's setup page.</p>
      <p><b>Audio is kept</b> for ${esc(String(state.config.retention_days ?? 90))} days by default; the verdicts are kept so progress charts still work.</p>
      <p class="muted">Pesu is a practice aid, not a medical device and not a diagnosis.</p>
    </div>`;
}
