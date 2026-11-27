/* Pesu (பேசு): router and boot. ES modules, no framework, no build step (F8).
 *   #/                    who's using Pesu        #/privacy            privacy page
 *   #/pin                 therapist PIN           #/t                  roster
 *   #/t/:id               setup                   #/t/:id/record       record voice
 *   #/t/:id/review        review + overrides      #/t/:id/mic          mic test / simulator
 *   #/p                   pick child              #/p/:id              today
 *   #/p/:id/practice      the voice flow          #/p/:id/summary/:sid summary
 *   #/p/:id/garden        sticker garden
 */
"use strict";
import { viewGarden, viewPickChild, viewPrivacy, viewSummary, viewToday } from "./parent.js";
import { viewPractice } from "./practice.js";
import { viewChildren, viewMicTest, viewPin, viewRecord, viewReview, viewSetup } from "./therapist.js";
import { ApiError, api, esc, state } from "./util.js";

const $banner = document.getElementById("banner");
let pinReturn = "#/t";

const navigate = (hash) => { if (location.hash === hash) route(); else location.hash = hash; };

function viewRoles(view) {
  view.innerHTML = `
    <h1 class="brand"><img src="img/icon.svg" alt="" width="44" height="44"> பேசு · Pesu<span class="en">Home speech practice in Tamil, in the therapist's own voice</span></h1>
    <h2>யார் use பண்றீங்க?<span class="en">Who's using Pesu?</span></h2>
    <div class="roles">
      <a class="role" href="#/t"><span class="icon" aria-hidden="true">🩺</span><b>சிகிச்சையாளர்</b><span class="en">Therapist</span></a>
      <a class="role" href="#/p"><span class="icon" aria-hidden="true">👨‍👩‍👧</span><b>பெற்றோர்</b><span class="en">Parent</span></a>
    </div>
    <p class="muted small">Practice aid, not a medical device. <a href="#/privacy">Privacy</a> · v${esc(state.config.version)}</p>`;
}

const routes = [
  [/^#?\/?$/, (v) => viewRoles(v)],
  [/^#\/privacy$/, (v) => viewPrivacy(v)],
  [/^#\/pin$/, (v) => viewPin(v, navigate, pinReturn)],
  [/^#\/t$/, (v) => viewChildren(v, navigate), true],
  [/^#\/t\/([\w-]+)$/, (v, id) => viewSetup(v, id, navigate), true],
  [/^#\/t\/([\w-]+)\/record$/, (v, id) => viewRecord(v, id), true],
  [/^#\/t\/([\w-]+)\/review$/, (v, id, q) => viewReview(v, id, q), true],
  [/^#\/t\/([\w-]+)\/mic$/, (v, id) => viewMicTest(v, id), true],
  [/^#\/p$/, (v) => viewPickChild(v)],
  [/^#\/p\/([\w-]+)$/, (v, id) => viewToday(v, id, navigate)],
  [/^#\/p\/([\w-]+)\/practice$/, (v, id) => viewPractice(v, id, navigate)],
  [/^#\/p\/([\w-]+)\/summary\/([\w-]+)$/, (v, id, sid, q) => viewSummary(v, id, sid, q)],
  [/^#\/p\/([\w-]+)\/garden$/, (v, id) => viewGarden(v, id)],
];

async function route() {
  const [path, qs] = (location.hash || "#/").split("?");
  const query = new URLSearchParams(qs || "");
  const current = document.getElementById("view");
  if (typeof current.cleanup === "function") { const c = current.cleanup; current.cleanup = null; await c(); }
  document.body.classList.remove("child");
  for (const [re, fn, therapistOnly] of routes) {
    const m = path.match(re);
    if (!m) continue;
    if (therapistOnly && !state.therapist) { pinReturn = location.hash; return navigate("#/pin"); }
    const fresh = current.cloneNode(false);       // drop old delegated listeners and handlers
    current.replaceWith(fresh);
    fresh.id = "view";
    try { await fn(fresh, ...m.slice(1), query); window.scrollTo(0, 0); }
    catch (err) { handleError(err, fresh); }
    return;
  }
  navigate("#/");
}

// F9: one error boundary. Kind message + a way home, never a blank screen.
function handleError(err, view = document.getElementById("view")) {
  if (err?.name === "SessionAborted") return;
  console.error("[pesu]", err);
  if (err instanceof ApiError && err.status === 401) { state.therapist = false; pinReturn = location.hash; return navigate("#/pin"); }
  view.innerHTML = `<div class="card"><b>ஏதோ தவறு நடந்துடுச்சு.</b><span class="en">Something went wrong: ${esc(err?.message || err)}</span>
    <p><a class="btn primary" href="#/">Go home</a></p></div>`;
}
window.addEventListener("unhandledrejection", (e) => { if (e.reason?.name !== "SessionAborted") { console.error("[pesu]", e.reason); } });

(async function boot() {
  try {
    state.config = await api("/api/config");
    state.therapist = (await api("/api/auth")).therapist;
  } catch (e) {
    document.getElementById("view").innerHTML = `<p>Pesu's server isn't answering. Is it running? (${esc(e.message)})</p>`;
    return;
  }
  const notes = [];
  if (state.config.demo) document.body.classList.add("demo");
  if (!window.isSecureContext) notes.push("Open Pesu at http://localhost:3000 (or over HTTPS): browsers only allow the microphone on secure pages.");
  if (!(window.SpeechRecognition || window.webkitSpeechRecognition))
    notes.push(state.config.demo ? "This browser has no speech recognition: use Judge Mode on the practice screen, or open in Chrome."
      : "This browser has no speech recognition: Pesu will record tries for the therapist. For instant feedback, open in Chrome.");
  if (notes.length) { $banner.innerHTML = notes.map(esc).join("<br>"); $banner.classList.remove("hidden"); }
  window.addEventListener("hashchange", route);
  route();
})();
