/**
 * Lane County Hot Jobs traffic counter (Cloudflare Worker + D1).
 *
 * The widget sends three anonymous signals: "load" (widget drawn), "view" (scrolled into view) and
 * "apply" (a "View and apply" click, with the employer and type of work). Nothing is stored that
 * identifies a person: no cookies, no IP addresses. A visitor key is a hash of a secret, the date, the
 * IP address, the browser and the site, so the same person counts once per site per day and cannot be
 * followed across days or sites.
 */
const EVENTS = new Set(["load", "view", "apply"]);
const BOT = /bot|crawl|spider|slurp|headless|lighthouse|pingdom|monitor|preview/i;
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
               "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400" };

function hostOf(u) {
  try { return new URL(u).hostname.toLowerCase().replace(/^www\./, ""); } catch (e) { return ""; }
}
function clip(s, n) { return String(s || "").replace(/[\u0000-\u001f|]/g, " ").trim().slice(0, n || 120); }

async function visitorKey(secret, day, ip, ua, host) {
  const data = new TextEncoder().encode(`${secret}|${day}|${ip}|${ua}|${host}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].slice(0, 10).map(b => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (url.pathname !== "/e" || req.method !== "POST") {
      return new Response("Lane County Hot Jobs traffic counter", { headers: { ...CORS, "Content-Type": "text/plain" } });
    }
    const ua = req.headers.get("User-Agent") || "";
    if (BOT.test(ua)) return new Response(null, { status: 204, headers: CORS });
    let b;
    try { b = JSON.parse((await req.text()).slice(0, 2000)); } catch (e) { return new Response(null, { status: 400, headers: CORS }); }
    const ev = String(b.e || "");
    if (!EVENTS.has(ev)) return new Response(null, { status: 400, headers: CORS });
    // The browser reports the hosting page in Origin/Referer; fall back to what the widget sent.
    const host = (hostOf(req.headers.get("Referer")) || hostOf(req.headers.get("Origin")) || clip(b.h, 100).toLowerCase()).slice(0, 100);
    if (!host || !/^[a-z0-9.-]+$/.test(host)) return new Response(null, { status: 400, headers: CORS });
    const day = new Date().toLocaleDateString("en-CA", { timeZone: "America/Los_Angeles" });  // Pacific calendar day
    const label = ev === "apply" ? `${clip(b.emp, 100)}|${clip(b.t, 60)}` : "";
    const ip = req.headers.get("CF-Connecting-IP") || "";
    const v = await visitorKey(env.SALT || "", day, ip, ua, host);
    const all = await visitorKey(env.SALT || "", day, ip, ua, "*");  // same person across every hosting site
    ctx.waitUntil(env.DB.batch([
      env.DB.prepare("INSERT INTO daily (day, host, event, label, n) VALUES (?1, ?2, ?3, ?4, 1) " +
                     "ON CONFLICT (day, host, event, label) DO UPDATE SET n = n + 1").bind(day, host, ev, label),
      env.DB.prepare("INSERT OR IGNORE INTO visitors (day, host, event, v) VALUES (?1, ?2, ?3, ?4)").bind(day, host, ev, v),
      env.DB.prepare("INSERT OR IGNORE INTO visitors (day, host, event, v) VALUES (?1, '*', ?2, ?3)").bind(day, ev, all),
    ]));
    return new Response(null, { status: 204, headers: CORS });
  },

  async scheduled(event, env) {
    await env.DB.prepare("DELETE FROM visitors WHERE day < date('now', '-36 days')").run();
  },
};
