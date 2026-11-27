// Therapist screens: PIN, roster, setup, voice recording, review, mic test (D1-D13 subset, A5, A11, A14).
"use strict";
import { Mic } from "./mic.js";
import { setMeter } from "./practice.js";
import { playUrl } from "./sound.js";
import { api, esc, fmtDay, fmtDayOnly, fmtTime, on, picture, send, state, wordById, wordLabel } from "./util.js";

const VERDICT_LABEL = { correct: "✓ சரி · correct (k)", error_t: "✗ t கேட்டது · heard t", unsure: "? தெரியல · unsure", unscored: "◌ மதிப்பிடல · not scored" };

export function viewPin(view, navigate, back = "#/t") {
  view.innerHTML = `
    <a class="back" href="#/">← Back</a>
    <h1>PIN<span class="en">Therapist screens are behind a PIN so a child can't wander in.${state.config.demo ? " Demo PIN: 1234" : ""}</span></h1>
    <form id="f" class="row"><input id="pin" inputmode="numeric" autocomplete="off" maxlength="6" placeholder="••••" aria-label="PIN">
      <button class="primary">Open</button></form>
    <p id="msg" class="muted" role="alert"></p>`;
  document.getElementById("pin").focus();
  document.getElementById("f").onsubmit = async (e) => {
    e.preventDefault();
    const r = await send("/api/pin", { pin: document.getElementById("pin").value });
    const msg = document.getElementById("msg");
    if (r.ok) { state.therapist = true; navigate(back); }
    else msg.textContent = r.locked_for ? `Too many tries. Wait ${r.locked_for} s.` : "தவறான PIN · Wrong PIN";
  };
}

export async function viewChildren(view, navigate) {
  const [kids, auth] = await Promise.all([api("/api/children"), api("/api/auth")]);
  const today = new Date().toISOString().slice(0, 10);
  const daysSince = (d) => d ? Math.round((Date.parse(today) - Date.parse(d)) / 86400000) : null;
  view.innerHTML = `
    <div class="row"><a class="back" href="#/">← Home</a><span class="spacer"></span><button id="logout">Lock</button></div>
    <h1>குழந்தைகள்<span class="en">Children</span></h1>
    ${auth.pin_is_default ? '<p class="warn">The PIN is still the default. Change it below.</p>' : ""}
    <input id="search" placeholder="Search" aria-label="Search children">
    <table class="roster"><thead><tr><th>Child</th><th>Today</th><th>Last practised</th><th>Needs review</th><th></th></tr></thead>
    <tbody>${kids.map((k) => {
      const gap = daysSince(k.last_practised);
      return `<tr data-name="${esc(k.name.toLowerCase())}">
        <td><a href="#/t/${k.id}"><b>${esc(k.name)}</b></a> <span class="muted">${k.age} yrs</span> ${k.is_sample ? '<span class="tag">DEMO</span>' : ""}</td>
        <td>${k.today.tries}/${k.today.goal}</td>
        <td>${k.last_practised ? fmtDayOnly(k.last_practised) : "—"} ${gap != null && gap >= 3 ? '<span class="red-dot" title="3+ days without practice">●</span>' : ""}</td>
        <td>${k.needs_review ? `<b>${k.needs_review}</b>` : "0"}</td>
        <td><a class="btn" href="#/t/${k.id}/review">Review →</a></td></tr>`;
    }).join("")}</tbody></table>
    <h2>குழந்தையை சேர்க்க<span class="en">Add a child</span></h2>
    <form id="add" class="row">
      <input name="name" placeholder="Name" required maxlength="60" aria-label="Name">
      <input name="age" type="number" min="2" max="12" placeholder="Age" required aria-label="Age" class="narrow">
      <input name="note" placeholder="Clinical note (therapist only)" maxlength="200" aria-label="Note" class="grow">
      <button class="primary">Add</button>
    </form>
    <h2>Settings</h2>
    <form id="pinform" class="row"><input id="newpin" inputmode="numeric" pattern="\\d{4,6}" placeholder="New PIN (4-6 digits)" aria-label="New PIN">
      <button>Change PIN</button><span id="pinmsg" class="muted"></span></form>
    ${state.config.demo ? '<p><button id="rmdemo">Remove demo data</button> <span class="muted">Deletes the sample child and all sample tries.</span></p>' : ""}`;
  document.getElementById("search").oninput = (e) => {
    const q = e.target.value.toLowerCase();
    view.querySelectorAll("tbody tr").forEach((tr) => tr.classList.toggle("hidden", !tr.dataset.name.includes(q)));
  };
  document.getElementById("logout").onclick = async () => { await send("/api/logout", {}); state.therapist = false; navigate("#/"); };
  document.getElementById("add").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const kid = await send("/api/children", { name: f.get("name"), age: Number(f.get("age")), note: f.get("note") });
    navigate(`#/t/${kid.id}`);
  };
  document.getElementById("pinform").onsubmit = async (e) => {
    e.preventDefault();
    const pin = document.getElementById("newpin").value;
    try { await send("/api/pin/change", { new_pin: pin }); document.getElementById("pinmsg").textContent = "PIN changed ✓"; }
    catch { document.getElementById("pinmsg").textContent = "Use 4-6 digits"; }
  };
  document.getElementById("rmdemo")?.addEventListener("click", async () => {
    await send("/api/demo/remove", {}); viewChildren(view, navigate);
  });
}

export async function viewSetup(view, id, navigate) {
  const kid = await api(`/api/children/${id}`);
  const selected = new Set(kid.word_ids);
  const t = state.config.target;
  const cov = kid.coverage;
  const lf = kid.listen_first == null ? "auto" : kid.listen_first ? "on" : "off";
  view.innerHTML = `
    <a class="back" href="#/t">← Children</a>
    <h1>${esc(kid.name)} · இந்த வாரம்<span class="en">This week's target · <span id="saved" class="ok"></span></span></h1>
    <div class="card">
      <div class="row"><b>இலக்கு · Target:</b> ${t.target_letter} (k) at the start of a word <span class="tag teal">active</span></div>
      <div class="row muted"><b>கவனிக்க · Listen for:</b> ${t.error_letters.join(" / ")} (t) instead</div>
      <div class="row muted">ர (r) <span class="tag">விரைவில் · coming soon</span> ழ (zh) <span class="tag">விரைவில் · coming soon</span></div>
    </div>
    <h2>வார்த்தைகள் (3–6)<span class="en">Word set: tap to choose. Saves automatically.</span></h2>
    <div class="words">${state.config.words.map((w) => `
      <button class="word ${selected.has(w.id) ? "on" : ""}" data-id="${w.id}" aria-pressed="${selected.has(w.id)}">
        ${picture(w, "pic")}<b>${w.tamil}</b><span class="en">${w.latin} · ${w.english[0]}</span></button>`).join("")}
    </div>
    <h2>Practice settings</h2>
    <div class="row">
      <label>Sessions/day <select id="spd">${[1, 2, 3].map((n) => `<option ${n === kid.sessions_per_day ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label>Tries/session <select id="tps">${[5, 7, 10].map((n) => `<option ${n === kid.tries_per_session ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label>"Listen first" (hear the word 3× before trying)
        <select id="lf"><option value="auto" ${lf === "auto" ? "selected" : ""}>Auto (on for age ≤ 3)</option>
        <option value="on" ${lf === "on" ? "selected" : ""}>On</option><option value="off" ${lf === "off" ? "selected" : ""}>Off</option></select></label>
    </div>
    <h2>பெற்றோருக்கு குறிப்பு<span class="en">Note to parent (shown on their Today screen)</span></h2>
    <textarea id="note" maxlength="200">${esc(kid.parent_note)}</textarea>
    <p class="${cov.cues < cov.total ? "warn" : "muted"}">Your voice: ${cov.prompts}/${cov.total} prompts, ${cov.cues}/${cov.total} model cues recorded.
      ${cov.cues < cov.total ? "Words without a recorded cue skip the model sound (text-to-speech may not say க correctly)." : ""}</p>
    <div class="row">
      <a class="btn primary" href="#/t/${id}/record">🎙️ Record your voice</a>
      <a class="btn" href="#/t/${id}/review">Week review</a>
      <a class="btn" href="#/t/${id}/mic">Mic test</a>
      <a class="btn" href="/api/children/${id}/export" download>⬇ Export ZIP</a>
      ${state.config.demo ? '<button id="ff">Fast-forward 2 weeks (sample data)</button>' : ""}
    </div>
    <details class="card danger"><summary>Delete ${esc(kid.name)}'s data</summary>
      <p>Removes every try, verdict, session and audio file for this child. Type the name to confirm.</p>
      <div class="row"><input id="confirm" placeholder="${esc(kid.name)}" aria-label="Type the child's name"><button id="del" class="danger-btn">Delete forever</button></div>
    </details>`;

  let timer = null;
  const saveNow = async () => {
    if (selected.size < 3) { document.getElementById("saved").textContent = "Pick at least 3 words"; return; }
    const lfv = document.getElementById("lf").value;
    await send(`/api/children/${id}`, {
      word_ids: state.config.words.map((w) => w.id).filter((w) => selected.has(w)),
      sessions_per_day: Number(document.getElementById("spd").value),
      tries_per_session: Number(document.getElementById("tps").value),
      parent_note: document.getElementById("note").value,
      ...(lfv === "auto" ? {} : { listen_first: lfv === "on" }),
    }, "PUT");
    document.getElementById("saved").textContent = "Saved ✓";
  };
  const autosave = () => { document.getElementById("saved").textContent = "Saving…"; clearTimeout(timer); timer = setTimeout(saveNow, 500); };
  on(view, "click", ".word", (_, el) => {
    const wid = el.dataset.id;
    if (selected.has(wid)) selected.delete(wid); else if (selected.size < 6) selected.add(wid);
    el.classList.toggle("on", selected.has(wid)); el.setAttribute("aria-pressed", selected.has(wid));
    autosave();
  });
  ["spd", "tps", "lf"].forEach((x) => (document.getElementById(x).onchange = autosave));
  document.getElementById("note").oninput = autosave;
  document.getElementById("ff")?.addEventListener("click", async (e) => {
    const r = await send(`/api/children/${id}/demo/fast-forward`, {});
    e.target.textContent = `Added ${r.added} sample tries ✓`;
  });
  document.getElementById("del").onclick = async () => {
    try {
      await api(`/api/children/${id}?confirm_name=${encodeURIComponent(document.getElementById("confirm").value)}`, { method: "DELETE" });
      navigate("#/t");
    } catch (e) { alertInline(view, e.message); }
  };
}

function alertInline(view, text) {
  const p = document.createElement("p"); p.className = "warn"; p.textContent = text; view.appendChild(p);
}

export async function viewRecord(view, id) {
  const kid = await api(`/api/children/${id}`);
  const have = new Set(kid.coverage.have);
  const row = (w, kind, label) => `
    <div class="clip" data-word="${w.id}" data-kind="${kind}">
      <span class="cliplabel">${label}: <b lang="ta">“${esc(w[kind])}”</b><span class="en">${kind === "prompt" ? `“Say ${w.latin}!”` : `“From the throat… ${w.latin}”`}</span></span>
      <button class="hold">🎙️ Hold to record</button>
      <button class="play" ${have.has(`${w.id}:${kind}`) ? "" : "disabled"} aria-label="Play">▶</button>
      <span class="status">${have.has(`${w.id}:${kind}`) ? '<span class="ok">✓ your voice</span>' : '<span class="tag">not recorded</span>'}</span>
      <div class="meter mini"><i></i></div>
    </div>`;
  view.innerHTML = `
    <a class="back" href="#/t/${id}">← Setup</a>
    <h1>உங்க குரல்<span class="en">Record your voice: the child hears you, not a robot</span></h1>
    <p class="muted">Hold, speak, release. Clips under 0.4 s or too quiet are rejected. The <b>model cue</b> matters most: without it Pesu skips the model sound for that word.</p>
    ${kid.word_ids.map(wordById).map((w) => `
      <div class="rec-row">${picture(w, "pic")}<div>${row(w, "prompt", "Prompt")}${row(w, "cue", "Model cue")}</div></div>`).join("")}
    <div class="row"><a class="btn primary" href="#/t/${id}/review">Done → Week review</a></div>`;

  view.querySelectorAll(".clip").forEach((el) => {
    const { word, kind } = el.dataset;
    const hold = el.querySelector(".hold"), play = el.querySelector(".play"), status = el.querySelector(".status");
    let mic = null, recorder = null, chunks = [], peak = 0, started = 0, live = false;
    const start = async (e) => {
      e.preventDefault();
      mic = new Mic();
      try { await mic.open(); } catch { status.textContent = "Mic blocked"; return; }
      chunks = []; peak = 0; started = performance.now(); live = true;
      recorder = new MediaRecorder(mic.stream);
      recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
      recorder.start(); hold.classList.add("recording"); hold.textContent = "● Recording…";
      (async () => { while (live) { const r = mic.rms(); peak = Math.max(peak, r); setMeter(el.querySelector(".meter"), r); await new Promise((x) => setTimeout(x, 60)); } })();
    };
    const stop = async () => {
      if (!recorder || recorder.state !== "recording") return;
      live = false;
      await new Promise((r) => { recorder.onstop = r; recorder.stop(); });
      mic.close();
      hold.classList.remove("recording"); hold.textContent = "🎙️ Hold to record";
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      if (performance.now() - started < 400 || blob.size < 2000) { status.textContent = "Too short: hold longer"; return; }
      if (peak < 0.03) { status.textContent = "Too quiet: move closer"; return; }
      const fd = new FormData(); fd.append("audio", blob, "clip.webm");
      try { await api(`/api/children/${id}/clips/${word}/${kind}`, { method: "PUT", body: fd }); }
      catch (err) { status.textContent = err.message; return; }
      status.innerHTML = `<span class="ok">✓ your voice</span>${peak > 0.95 ? ' <span class="warn">(clipped: speak softer)</span>' : ""}`;
      play.disabled = false;
    };
    hold.addEventListener("pointerdown", start);
    hold.addEventListener("pointerup", stop);
    hold.addEventListener("pointerleave", stop);
    play.onclick = () => playUrl(`/api/children/${id}/clips/${word}/${kind}?t=${Date.now()}`).catch(() => {});
  });
}

function bars(days) {
  const w = 640, h = 170, pad = 26, bw = (w - pad * 2) / days.length;
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Percent of scored tries correct per day">
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#cfd8db"/>
    ${days.map((d, i) => {
      const pct = d.scored ? Math.round((100 * d.correct) / d.scored) : 0;
      const bh = ((h - pad * 2) * pct) / 100, x = pad + i * bw + bw * 0.18;
      return `<rect x="${x}" y="${h - pad - bh}" width="${bw * 0.64}" height="${bh}" rx="3" fill="#0f766e"/>
        <text x="${x + bw * 0.32}" y="${h - pad - bh - 4}" text-anchor="middle">${d.scored ? pct + "%" : "–"}</text>
        <text x="${x + bw * 0.32}" y="${h - 8}" text-anchor="middle">${fmtDayOnly(d.day)}</text>`;
    }).join("")}</svg>`;
}

// D5: unsure / unscored first, then parent-decided, then Pesu with low confidence, then the rest; reviewed last.
function reviewRank(a) {
  if (a.therapist_reviewed) return 5;
  if (a.verdict === "unsure" || a.verdict === "unscored") return 0;
  if (a.decided_by === "parent") return 1;
  if (a.confidence != null && a.confidence > 0 && a.confidence < 0.6) return 2;
  return 3;
}

export async function viewReview(view, id, query) {
  const days = Number(query.get("days") || 7);
  const [kid, data] = await Promise.all([api(`/api/children/${id}`), api(`/api/children/${id}/attempts?days=${days}`)]);
  const rows = [...data.attempts].sort((a, b) => reviewRank(a) - reviewRank(b) || b.ts.localeCompare(a.ts));
  const trouble = data.most_trouble ? wordById(data.most_trouble) : null;
  const ag = data.agreement;
  view.innerHTML = `
    <a class="back" href="#/t/${id}">← Setup</a>
    <h1>${esc(kid.name)} · Review<span class="en">Last ${days} days ·
      <a href="#/t/${id}/review?days=7">7</a> · <a href="#/t/${id}/review?days=14">14</a> · <a href="#/t/${id}/review?days=28">28</a> days</span></h1>
    <p><b>${data.correct}/${data.scored} scored tries correct.</b> ${trouble ? `Most trouble with ${trouble.tamil} · ${trouble.latin} (${trouble.english[0]}).` : ""}
      ${data.counts.unsure} unsure, ${data.counts.unscored} not scored.</p>
    <p class="note-line">Pesu agrees with you on <b>${ag.agree} of ${ag.reviewed}</b> reviewed tries${ag.reviewed < 20 ? " (small sample)" : ""}.
      Verdicts are a first pass; your ear is final.</p>
    ${bars(data.days)}
    <table class="perword"><caption>By word</caption><thead><tr><th>Word</th><th>Correct</th><th>Agreement</th></tr></thead><tbody>
      ${data.per_word.map((p) => { const w = wordById(p.word_id); return `<tr><td>${picture(w, "thumb")} ${wordLabel(w)}</td>
        <td>${p.correct}/${p.scored}</td><td>${p.agree}/${p.reviewed}</td></tr>`; }).join("")}</tbody></table>
    <h2>Tries <span class="en">Keys: ↑/↓ move · Space play · C correct · T t-error · U unsure</span></h2>
    <table class="review"><thead><tr><th>When</th><th>Word</th><th>Audio</th><th>Pesu said</th><th>Now</th><th>Set</th><th class="hide-sm">Heard (raw)</th></tr></thead>
    <tbody>${rows.map((a, i) => {
      const w = wordById(a.word_id);
      const trail = a.events.map((e) => `${fmtTime(e.ts)} ${e.actor}: ${e.from_verdict || "–"} → ${e.to_verdict}${e.note ? ` (“${esc(e.note)}”)` : ""}`).join("<br>");
      return `<tr data-i="${i}" data-id="${a.id}" tabindex="0" class="${a.therapist_reviewed ? "reviewed" : ""}">
        <td>${fmtDay(a.ts)} ${fmtTime(a.ts)} ${a.is_sample ? '<span class="tag">sample</span>' : ""}</td>
        <td>${picture(w, "thumb")} ${wordLabel(w)}</td>
        <td>${a.has_audio ? `<button data-play="${a.id}" aria-label="Play">▶</button>` : '<span class="muted">—</span>'}</td>
        <td><span class="verdict v-${a.pesu_verdict}">${VERDICT_LABEL[a.pesu_verdict] || a.pesu_verdict}</span>
          ${a.confidence ? `<span class="muted small">${Math.round(a.confidence * 100)}%</span>` : ""}</td>
        <td><span class="verdict v-${a.verdict}">${VERDICT_LABEL[a.verdict]}</span> <span class="tag ${a.decided_by === "therapist" ? "teal" : ""}">${a.decided_by}</span>
          ${trail ? `<details class="trail"><summary>history</summary>${trail}</details>` : ""}</td>
        <td class="set"><button data-v="correct" title="C">✓</button><button data-v="error_t" title="T">✗</button><button data-v="unsure" title="U">?</button>
          <input class="note" maxlength="200" placeholder="note" aria-label="Note"></td>
        <td class="hide-sm">${esc(a.transcript) || '<span class="muted">(nothing)</span>'}</td></tr>`;
    }).join("") || '<tr><td colspan="7" class="muted">No tries in this period.</td></tr>'}</tbody></table>`;

  const play = (aid) => playUrl(`/api/attempts/${aid}/audio`).catch(() => {});
  const setVerdict = async (tr, v) => {
    await send(`/api/attempts/${tr.dataset.id}`, { verdict: v, note: tr.querySelector(".note").value }, "PATCH");
    const keep = Number(tr.dataset.i);
    await viewReview(view, id, query);
    view.querySelector(`tr[data-i="${Math.min(keep, rows.length - 1)}"]`)?.focus();
  };
  // Property handlers (not addEventListener) so re-rendering in place never stacks duplicates.
  view.onclick = (e) => {
    const p = e.target.closest("[data-play]");
    if (p) return play(p.dataset.play);
    const b = e.target.closest(".set button");
    if (b) setVerdict(b.closest("tr"), b.dataset.v);
  };
  const trs = [...view.querySelectorAll("tbody tr[data-id]")];
  trs.forEach((tr) => tr.addEventListener("focus", () => { if (tr.querySelector("[data-play]")) play(tr.dataset.id); }));
  view.onkeydown = (e) => {
    const tr = document.activeElement?.closest?.("tr[data-id]");
    if (!tr || e.target.matches("input")) return;
    const i = trs.indexOf(tr);
    const keys = { c: "correct", t: "error_t", u: "unsure" };
    if (e.key === "ArrowDown" || e.key === "ArrowRight") { trs[i + 1]?.focus(); e.preventDefault(); }
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") { trs[i - 1]?.focus(); e.preventDefault(); }
    else if (e.key === " ") { play(tr.dataset.id); e.preventDefault(); }
    else if (keys[e.key.toLowerCase()]) setVerdict(tr, keys[e.key.toLowerCase()]);
  };
  trs[0]?.focus({ preventScroll: true });
}

export async function viewMicTest(view, id) {
  const kid = await api(`/api/children/${id}`);
  view.innerHTML = `
    <a class="back" href="#/t/${id}">← Setup</a>
    <h1>Mic test<span class="en">See exactly what Pesu heard and decided. Nothing is saved.</span></h1>
    <div class="row">${kid.word_ids.map(wordById).map((w, i) =>
      `<label class="tag"><input type="radio" name="w" value="${w.id}" ${i ? "" : "checked"}> ${w.tamil} · ${w.latin} (${w.english[0]})</label>`).join("")}</div>
    <div class="row"><button class="primary big" id="go">🎙️ Listen 4 s</button></div>
    <div class="meter" id="meter"><i></i></div>
    <h2>Simulate the recogniser<span class="en">Type alternatives separated by commas, e.g. டாக்கா, காக்கா</span></h2>
    <form id="sim" class="row"><input id="alts" class="grow" value="டாக்கா, காக்கா" aria-label="Alternatives">
      <input id="conf" class="narrow" value="0.8" aria-label="Top confidence"><input id="noise" class="narrow" value="0.01" aria-label="Noise"><button>Score</button></form>
    <pre id="out" class="card">—</pre>`;
  const wid = () => view.querySelector("input[name=w]:checked").value;
  const show = (alts, confs, noise, s, extra = "") => {
    document.getElementById("out").textContent =
      `${extra}Alternatives:${alts.length ? alts.map((a, i) => `\n  ${i + 1}. ${a}${confs[i] ? `  (conf ${confs[i].toFixed(2)})` : ""}`).join("") : " (none)"}\n` +
      `Noise: ${noise.toFixed(3)} (threshold ${state.config.noise_threshold})\n\nVerdict: ${s.verdict}   reason: ${s.reason}\nPesu says: ${s.say_ta}  (${s.say_en})`;
  };
  document.getElementById("go").onclick = async () => {
    const { SpeechRec, listen } = await import("./mic.js");
    if (!SpeechRec) { document.getElementById("out").textContent = "Speech recognition needs Chrome. Use the simulator below."; return; }
    const mic = new Mic();
    try { await mic.open(); } catch { document.getElementById("out").textContent = "Mic blocked."; return; }
    const before = await mic.measure(600, (r) => setMeter(document.getElementById("meter"), r));
    document.getElementById("out").textContent = "Listening…";
    const heard = await listen(mic, { windowMs: 4000, background: before, session: {}, onLevel: (r) => setMeter(document.getElementById("meter"), r) });
    mic.close();
    const s = await send("/api/score", { word_id: wid(), alternatives: heard.alternatives, confidences: heard.confidences, noise_rms: heard.noise });
    show(heard.alternatives, heard.confidences, heard.noise, s, `${heard.error ? `Recogniser error: ${heard.error}\n` : ""}Onset: ${heard.latencyMs ?? "—"} ms\n`);
  };
  document.getElementById("sim").onsubmit = async (e) => {
    e.preventDefault();
    const alts = document.getElementById("alts").value.split(",").map((x) => x.trim()).filter(Boolean);
    const confs = [Number(document.getElementById("conf").value) || 0];
    const noise = Number(document.getElementById("noise").value) || 0;
    const s = await send("/api/score", { word_id: wid(), alternatives: alts, confidences: confs, noise_rms: noise });
    show(alts, confs, noise, s);
  };
}
