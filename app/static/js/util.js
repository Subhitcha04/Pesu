// Shared helpers: API calls, escaping, time formatting in the configured zone, small DOM helpers.
"use strict";

export const state = { config: null, therapist: false };

export class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}

export async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    if (res.status === 401) state.therapist = false;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.headers.get("content-type")?.includes("json") ? res.json() : res;
}

export const send = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const wordById = (id) => state.config.words.find((w) => w.id === id);

// A3: always format in PESU_TZ (sent by the server), never the device's zone guess.
const fmt = (opts) => new Intl.DateTimeFormat("en-IN", { timeZone: state.config?.tz || "Asia/Kolkata", ...opts });
export const fmtTime = (iso) => fmt({ hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
export const fmtDay = (iso) => fmt({ weekday: "short", day: "numeric" }).format(new Date(iso));
export const fmtDayOnly = (ymd) => fmt({ weekday: "short", day: "numeric" }).format(new Date(ymd + "T12:00:00Z"));

/** A word bank word as Tamil + English at the same size, e.g. "காக்கா · kaakka (crow)". */
export const wordLabel = (w) => `<span class="tw" lang="ta">${w.tamil}</span> <span class="tw"><span class="en" lang="en">· ${w.latin} (${esc(w.english[0])})</span></span>`;

export function picture(word, cls = "") {
  return word.picture
    ? `<img class="${cls}" src="img/words/${word.picture}" alt="${esc(word.english[0])}" draggable="false">`
    : `<span class="${cls} emoji" role="img" aria-label="${esc(word.english[0])}">${word.emoji}</span>`;
}

/** Event delegation, so no inline handlers are needed (CSP: script-src 'self'). */
export function on(root, event, selector, fn) {
  root.addEventListener(event, (e) => {
    const el = e.target.closest(selector);
    if (el && root.contains(el)) fn(e, el);
  });
}

// Tamil number words for natural speech ("ஏழுல நாலு"), 0-20; larger numbers fall back to digits.
const TA_NUM = ["பூஜ்ஜியம்", "ஒன்னு", "ரெண்டு", "மூணு", "நாலு", "அஞ்சு", "ஆறு", "ஏழு", "எட்டு", "ஒம்பது", "பத்து",
  "பதினொன்னு", "பன்னெண்டு", "பதிமூணு", "பதினாலு", "பதினஞ்சு", "பதினாறு", "பதினேழு", "பதினெட்டு", "பத்தொம்பது", "இருபது"];
export const taNum = (n) => TA_NUM[n] ?? String(n);
