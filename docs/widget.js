/*!
 * Lane County Hot Jobs widget
 * Embed on any site with one line:
 *   <script src="https://YOUR-HOST/widget.js" defer></script>
 * Optional settings on the same tag:
 *   data-type="Healthcare & human services"   start filtered to a type of work ("A|B" for several)
 *   data-workplace="Healthcare"               start filtered to a kind of workplace ("A|B" for several)
 *   data-hours="Full-time"                    start filtered to Full-time, Part-time or Temporary or seasonal
 *   data-city="Florence"                      start filtered to one city
 *   data-lang="es"                            start in Spanish (default: the visitor's browser language)
 *   data-title="Open healthcare jobs"         heading text
 *   data-target="my-div-id"                   draw inside an existing element
 * The widget reads jobs.json from the same folder as this file, so updating
 * that file updates every site that embeds the widget.
 * A link ending in #hotjobs=<id>.<id>... opens a list of jobs someone picked (see "Make a list for someone").
 */
(function () {
  "use strict";
  var me = document.currentScript;
  if (!me) return;
  var base = me.src.replace(/[^\/]*$/, "");
  // Anonymous counts for the staff traffic page: widget shown, scrolled into view, apply clicks, "still open?"
  // answers and list use. No cookies. Skipped when the browser asks not to be tracked.
  var COUNTER = "https://hot-jobs-analytics.collaborativeedo.workers.dev";
  var REPORT = "mailto:info@collaborativeedo.org?subject=" + encodeURIComponent("Hot Jobs: problem with a listing");
  var QR_LIB = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js";
  var MAX_LIST = 12;
  function signal(ev, extra) {
    try {
      if (!/^https:/.test(COUNTER) || navigator.globalPrivacyControl || navigator.doNotTrack === "1") return;
      if (!/^https?:$/.test(location.protocol) || /^(localhost|127\.)/.test(location.hostname)) return;
      var body = JSON.stringify(Object.assign({ e: ev, h: location.hostname }, extra || {}));
      var blob = new Blob([body], { type: "text/plain" });
      if (!(navigator.sendBeacon && navigator.sendBeacon(COUNTER + "/e", blob))) {
        fetch(COUNTER + "/e", { method: "POST", body: body, keepalive: true, mode: "no-cors" });
      }
    } catch (e) { /* counting must never affect the widget */ }
  }
  var opt = me.dataset || {};

  // ---- Words ------------------------------------------------------------------------------------------
  var T = {
    en: {
      title: "Open jobs in Lane County", loading: "Loading jobs…", lang: "Español", langLabel: "Ver en español",
      down: 'Job listings are not available right now. Try the <a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">QualityInfo Job Finder</a>.',
      search: "Search jobs or employers, e.g. nurse, CDL, PeaceHealth", searchLabel: "Search jobs or employers",
      town: "Town", allTowns: "All Lane County",
      what: "What you do", where: "Where you'd work", hours: "Hours", pick: "pick one or more",
      ease: "Fewer barriers", easeHint: "shows jobs that match everything you pick",
      clear: "Clear all filters", clearLower: "clear all filters", showing: "Showing: ", or: " or ", and: " and ",
      count: function (n, m) { return n + " of " + m + " openings"; },
      none: "No openings match. Try fewer filters or", more: "Show more jobs",
      noEmp: "Employer not listed", pay: "Pay: ", noPay: "Pay not listed. ", apply: "View and apply",
      when: function (d, dated) {
        var w = d <= 0 ? "today" : d === 1 ? "1 day ago" : d + " days ago";
        return dated === false ? "Added " + w : w.charAt(0).toUpperCase() + w.slice(1);
      },
      foot: function (upd) {
        return "Jobs from the Oregon Employment Department's " +
          '<a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">QualityInfo Job Finder</a> and employers\' own hiring sites' +
          (upd ? ". Updated " + upd : "") +
          ". Average pay figures come from Oregon Employment Department wage data for the occupation, not from the posting. Not every opening is posted online. This is a pilot." +
          ' See a problem with a listing? <a href="' + REPORT + '">Let us know</a>.';
      },
      ask: "Was this job still open?", yes: "Yes", no: "No", thanks: "Thanks. That helps keep the list accurate.",
      makeList: "Make a list for someone", listHint: "Pick up to " + MAX_LIST + " jobs, then copy a link, show a QR code, or print a one-page list.",
      addToList: "Add to list", picked: function (n) { return n + " picked"; }, copy: "Copy link", copied: "Link copied",
      qr: "QR code", print: "Print", done: "Done", copyHere: "Copy this link:",
      listFor: function (n) { return "A list of " + n + " job" + (n === 1 ? "" : "s") + " picked for you"; },
      gone: function (k) { return k + (k === 1 ? " job on this list is" : " jobs on this list are") + " no longer listed."; },
      showAll: "Show all jobs", sheetTitle: "Jobs picked for you", scan: "Scan for the latest version of this list",
      daily: "Listings change daily. Check the link for the latest.", applyAt: "Apply:"
    },
    es: {
      title: "Empleos disponibles en el condado de Lane", loading: "Cargando empleos…", lang: "English", langLabel: "View in English",
      down: 'Los empleos no están disponibles en este momento. Pruebe el <a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">Job Finder de QualityInfo</a>.',
      search: "Busque empleos o empleadores, p. ej. enfermera, CDL, PeaceHealth", searchLabel: "Buscar empleos o empleadores",
      town: "Ciudad", allTowns: "Todo el condado de Lane",
      what: "Lo que hace", where: "Dónde trabajaría", hours: "Horario", pick: "elija una o más",
      ease: "Menos barreras", easeHint: "muestra empleos que cumplen todo lo que elija",
      clear: "Borrar todos los filtros", clearLower: "borre todos los filtros", showing: "Mostrando: ", or: " o ", and: " y ",
      count: function (n, m) { return n + " de " + m + " vacantes"; },
      none: "No hay vacantes que coincidan. Pruebe con menos filtros o", more: "Ver más empleos",
      noEmp: "Empleador no indicado", pay: "Pago: ", noPay: "Pago no indicado. ", apply: "Ver y solicitar",
      when: function (d, dated) {
        var w = d <= 0 ? "hoy" : d === 1 ? "hace 1 día" : "hace " + d + " días";
        return dated === false ? "Agregado " + w : w.charAt(0).toUpperCase() + w.slice(1);
      },
      foot: function (upd) {
        return "Empleos del " +
          '<a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">Job Finder de QualityInfo</a> del Departamento de Empleo de Oregón y de los sitios de contratación de los empleadores' +
          (upd ? ". Actualizado el " + upd : "") +
          ". Los promedios de pago provienen de los datos salariales del Departamento de Empleo de Oregón para la ocupación, no del anuncio. No todas las vacantes se publican en línea. Los anuncios aparecen tal como los publicó cada empleador, por lo general en inglés. Este es un proyecto piloto." +
          ' ¿Ve un problema con un anuncio? <a href="' + REPORT + '">Avísenos</a>.';
      },
      ask: "¿Seguía abierto este empleo?", yes: "Sí", no: "No", thanks: "Gracias. Eso nos ayuda a mantener la lista al día.",
      makeList: "Hacer una lista para alguien", listHint: "Elija hasta " + MAX_LIST + " empleos y luego copie un enlace, muestre un código QR o imprima una lista de una página.",
      addToList: "Agregar a la lista", picked: function (n) { return n + (n === 1 ? " elegido" : " elegidos"); }, copy: "Copiar enlace", copied: "Enlace copiado",
      qr: "Código QR", print: "Imprimir", done: "Listo", copyHere: "Copie este enlace:",
      listFor: function (n) { return "Una lista de " + n + (n === 1 ? " empleo elegido" : " empleos elegidos") + " para usted"; },
      gone: function (k) { return k + (k === 1 ? " empleo de esta lista ya no aparece." : " empleos de esta lista ya no aparecen."); },
      showAll: "Ver todos los empleos", sheetTitle: "Empleos elegidos para usted", scan: "Escanee para ver la versión más reciente de esta lista",
      daily: "Los anuncios cambian a diario. Consulte el enlace para ver lo más reciente.", applyAt: "Solicitar:"
    }
  };
  var ES_VALUES = {
    "Childcare & education": "Cuidado infantil y educación", "Construction & trades": "Construcción y oficios",
    "Creative & media": "Creativos y medios", "Engineering & science": "Ingeniería y ciencias",
    "Finance & accounting": "Finanzas y contabilidad", "Healthcare & human services": "Salud y servicios humanos",
    "Hospitality & leisure": "Hostelería y recreación", "Management & business": "Gerencia y negocios",
    "Manufacturing": "Manufactura", "Natural resources": "Recursos naturales",
    "Office & customer service": "Oficina y atención al cliente", "Other": "Otros", "Retail & sales": "Comercio y ventas",
    "Technology": "Tecnología", "Transportation & logistics": "Transporte y logística",
    "Healthcare": "Salud", "Education & childcare": "Educación y cuidado infantil", "Government": "Gobierno",
    "Retail": "Comercio", "Restaurants & hospitality": "Restaurantes y hostelería", "Banking & finance": "Banca y finanzas",
    "Automotive": "Automotriz", "Wood products & forestry": "Productos de madera y silvicultura",
    "Food & beverage": "Alimentos y bebidas", "Bioscience": "Biociencias",
    "Nonprofit & social services": "Organizaciones sin fines de lucro y servicios sociales",
    "Real estate & property": "Bienes raíces y propiedades", "Engineering & professional services": "Ingeniería y servicios profesionales",
    "Staffing agency": "Agencia de empleo",
    "Full-time": "Tiempo completo", "Part-time": "Medio tiempo", "Temporary or seasonal": "Temporal o de temporada", "Not stated": "No indicado"
  };
  var EASE = ["bus", "no_degree", "training", "fair_chance"];
  var EASE_LABEL = {
    en: { bus: "Near an LTD bus stop", no_degree: "No degree needed", training: "Training provided", fair_chance: "Fair-chance employer" },
    es: { bus: "Cerca de una parada de LTD", no_degree: "No se requiere título", training: "Ofrecen capacitación", fair_chance: "Empleador de segunda oportunidad" }
  };
  var EASE_TIP = {
    en: { bus: "The employer's address is within about a quarter mile of a Lane Transit District stop",
          no_degree: "The posting doesn't ask for a college degree, and says so or is in an occupation that usually needs a high school diploma or less",
          training: "The posting mentions paid or on-the-job training, an apprenticeship, or that they will train you",
          fair_chance: "The posting says the employer welcomes people with a criminal record" },
    es: { bus: "La dirección del empleador está a menos de un cuarto de milla de una parada de Lane Transit District",
          no_degree: "El anuncio no pide un título universitario y lo indica, o es una ocupación que por lo general requiere diploma de preparatoria o menos",
          training: "El anuncio menciona capacitación pagada o en el trabajo, un aprendizaje o que lo capacitarán",
          fair_chance: "El anuncio dice que el empleador acepta a personas con antecedentes penales" }
  };

  var CSS = [
    ".lchj{--a:#0f5c4d;--as:#dcebe6;--ink:#16231f;--mu:#56655f;--ln:#d3dbd7;--sk:#eef2f0;box-sizing:border-box;max-width:900px;margin:24px auto;padding:16px;border:1px solid var(--ln);border-radius:10px;background:#fff;color:var(--ink);font-size:15px;line-height:1.5;display:flex;flex-direction:column;gap:12px;text-align:left}",
    ".lchj *{box-sizing:border-box}",
    ".lchj [hidden]{display:none!important}",
    ".lchj .lchj-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px 12px}",
    ".lchj h2.lchj-h{margin:0;padding:0;font-size:22px;line-height:1.2;color:var(--ink);border:0;text-transform:none;letter-spacing:0}",
    ".lchj .lchj-meta{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}",
    ".lchj .lchj-count{font-size:13px;color:var(--mu)}",
    ".lchj button.lchj-link{font:inherit;font-size:13px;font-weight:600;color:var(--a);background:none;border:0;padding:0;margin:0;cursor:pointer;text-decoration:underline;text-underline-offset:3px;width:auto;text-transform:none;box-shadow:none;min-height:0}",
    ".lchj .lchj-controls{display:grid;grid-template-columns:1fr auto;gap:8px}",
    ".lchj input[type=search],.lchj select{font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--ln);border-radius:8px;background:#fff;color:var(--ink);min-width:0;width:100%;margin:0;height:auto;box-shadow:none}",
    ".lchj .lchj-group{display:flex;flex-direction:column;gap:6px}",
    ".lchj .lchj-label{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}",
    ".lchj .lchj-label small{font-weight:400;letter-spacing:0;text-transform:none;margin-left:6px}",
    ".lchj .lchj-chips{display:flex;flex-wrap:wrap;gap:6px}",
    ".lchj button.lchj-chip{font:inherit;font-size:13px;font-weight:500;border:1px solid var(--ln);background:#fff;color:var(--ink);border-radius:999px;padding:4px 10px;margin:0;cursor:pointer;line-height:1.4;text-transform:none;letter-spacing:0;box-shadow:none;min-height:0;width:auto}",
    ".lchj button.lchj-chip .n{font-size:11px;color:var(--mu);margin-left:4px}",
    ".lchj button.lchj-chip[aria-pressed=true]{background:var(--a);border-color:var(--a);color:#fff}",
    ".lchj button.lchj-chip[aria-pressed=true] .n{color:#fff;opacity:.8}",
    ".lchj button.lchj-chip:disabled{opacity:.4;cursor:default}",
    ".lchj .lchj-active,.lchj .lchj-banner{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px;color:var(--mu);background:var(--sk);border-radius:8px;padding:6px 10px}",
    ".lchj .lchj-banner{font-size:14px;color:var(--ink);padding:10px 12px}",
    ".lchj .lchj-banner b{font-weight:700}",
    ".lchj button.lchj-clear,.lchj button.lchj-ghost{font:inherit;font-size:13px;font-weight:600;border:1px solid var(--a);background:#fff;color:var(--a);border-radius:999px;padding:3px 12px;margin:0;cursor:pointer;width:auto;text-transform:none;box-shadow:none;min-height:0}",
    ".lchj .lchj-active button.lchj-clear,.lchj .lchj-banner button.lchj-ghost{margin-left:auto}",
    ".lchj button:focus-visible,.lchj input:focus-visible,.lchj select:focus-visible,.lchj a:focus-visible{outline:2px solid var(--a);outline-offset:2px}",
    ".lchj ul.lchj-jobs{list-style:none;margin:0;padding:0}",
    ".lchj li.lchj-job{display:flex;flex-direction:column;gap:3px;padding:14px 2px;margin:0;border-top:1px solid var(--ln);list-style:none}",
    ".lchj li.lchj-job::before{content:none}",
    ".lchj li.lchj-job.on{background:var(--sk);border-radius:6px;padding-left:8px;padding-right:8px}",
    ".lchj a.lchj-t{font-size:16px;font-weight:700;color:var(--a);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}",
    ".lchj a.lchj-t:hover{text-decoration-thickness:2px}",
    ".lchj .lchj-who{font-size:14px;color:var(--ink)}",
    ".lchj .lchj-who b{font-weight:600}",
    ".lchj .lchj-who .none{color:var(--mu);font-style:italic}",
    ".lchj .lchj-pay{font-size:14px;color:var(--ink)}",
    ".lchj .lchj-pay.typ{color:var(--mu);font-size:13px}",
    ".lchj .lchj-snip{font-size:13px;color:var(--mu);overflow-wrap:anywhere}",
    ".lchj .lchj-act{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin-top:4px}",
    ".lchj a.lchj-apply{display:inline-block;font-size:14px;font-weight:600;background:var(--a);color:#fff;text-decoration:none;border-radius:8px;padding:6px 14px}",
    ".lchj a.lchj-apply:hover{filter:brightness(1.12);color:#fff}",
    ".lchj .lchj-via{font-size:12px;color:var(--mu)}",
    ".lchj .lchj-when{font-size:12px;color:var(--mu);margin-left:auto;white-space:nowrap}",
    ".lchj label.lchj-pick{display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--a);cursor:pointer;margin:0 0 2px}",
    ".lchj label.lchj-pick input{width:18px;height:18px;margin:0;accent-color:var(--a)}",
    ".lchj .lchj-ask{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px;color:var(--ink);margin-top:6px}",
    ".lchj .lchj-ask button{font:inherit;font-size:13px;font-weight:600;border:1px solid var(--a);background:#fff;color:var(--a);border-radius:6px;padding:2px 12px;margin:0;cursor:pointer;width:auto;min-height:0;text-transform:none;box-shadow:none}",
    ".lchj .lchj-ask.done{color:var(--mu)}",
    ".lchj .lchj-empty{padding:20px 0;color:var(--mu)}",
    ".lchj button.lchj-more{align-self:center;font:inherit;font-size:14px;font-weight:600;border:1px solid var(--a);color:var(--a);background:#fff;border-radius:8px;padding:8px 16px;cursor:pointer;width:auto;text-transform:none}",
    ".lchj .lchj-tray{position:sticky;bottom:0;z-index:2;display:flex;flex-wrap:wrap;align-items:center;gap:8px;background:var(--a);color:#fff;border-radius:10px;padding:10px 12px;font-size:14px;box-shadow:0 -2px 12px rgba(0,0,0,.12)}",
    ".lchj .lchj-tray .lchj-hint{flex-basis:100%;font-size:12px;opacity:.9}",
    ".lchj .lchj-tray b{margin-right:auto}",
    ".lchj .lchj-tray button{font:inherit;font-size:13px;font-weight:600;border:1px solid #fff;background:#fff;color:var(--a);border-radius:8px;padding:5px 12px;margin:0;cursor:pointer;width:auto;min-height:0;text-transform:none;box-shadow:none}",
    ".lchj .lchj-tray button.alt{background:transparent;color:#fff}",
    ".lchj .lchj-tray button:disabled{opacity:.5;cursor:default}",
    ".lchj .lchj-tray input{flex:1 1 220px;font:inherit;font-size:13px;padding:5px 8px;border:0;border-radius:6px;color:var(--ink);min-width:0}",
    ".lchj .lchj-qr{display:flex;flex-direction:column;align-items:center;gap:6px;background:#fff;color:var(--ink);border-radius:8px;padding:12px;flex-basis:100%;font-size:12px}",
    ".lchj .lchj-qr img,.lchj .lchj-qr canvas{width:180px;height:180px}",
    ".lchj .lchj-foot{font-size:12px;color:var(--mu);border-top:1px solid var(--ln);padding-top:10px;margin:0}",
    ".lchj .lchj-foot a{color:var(--a)}",
    "@media (max-width:520px){.lchj .lchj-controls{grid-template-columns:1fr}.lchj{padding:12px}.lchj .lchj-when{margin-left:0}}"
  ].join("\n");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
    });
  }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  var lang = (opt.lang || store("lchj-lang") || (navigator.language || "en")).slice(0, 2) === "es" ? "es" : "en";
  function t(k) { return T[lang][k]; }
  function V(v) { return lang === "es" ? (ES_VALUES[v] || v) : v; }
  function payText(s) {
    if (lang !== "es" || !s) return s;
    return s.replace(/^Average for this occupation in Lane County:/, "Promedio de esta ocupación en el condado de Lane:")
      .replace(/ to /g, " a ").replace(/an hour/, "por hora").replace(/a year/, "al año").replace(/a month/, "al mes");
  }
  function viaText(s) {
    if (lang !== "es" || !s) return s;
    return s.replace(/^Apply through WorkSource Oregon$/, "Solicitar a través de WorkSource Oregon")
      .replace(/^Apply on the employer's site$/, "Solicitar en el sitio del empleador")
      .replace(/^Apply on (.+?)'s? site$/, "Solicitar en el sitio de $1")
      .replace(/^Apply on (.+)$/, "Solicitar en $1");
  }

  if (!document.getElementById("lchj-style")) {
    var stl = document.createElement("style");
    stl.id = "lchj-style";
    stl.textContent = CSS;
    document.head.appendChild(stl);
  }

  var root = el("div", "lchj");
  root.setAttribute("role", "region");
  var target = opt.target && document.getElementById(opt.target);
  if (target) target.appendChild(root); else me.parentNode.insertBefore(root, me.nextSibling);
  root.setAttribute("aria-label", opt.title || t("title"));
  root.innerHTML = '<div class="lchj-head"><h2 class="lchj-h"></h2><span class="lchj-count"></span></div>';
  root.querySelector(".lchj-h").textContent = opt.title || t("title");
  root.querySelector(".lchj-count").textContent = t("loading");

  fetch(base + "jobs.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () {
      root.querySelector(".lchj-count").textContent = "";
      root.appendChild(el("p", "lchj-empty", t("down")));
    });

  var OLD_INDUSTRY = { "Public sector": "Government", "Nonprofit": "Nonprofit & social services" };
  var HOURS = ["Full-time", "Part-time", "Temporary or seasonal", "Not stated"];
  function list(v) { return v ? String(v).split("|").map(function (x) { return x.trim(); }).filter(Boolean) : []; }
  function hashIds() {
    var m = /(?:^#|&)hotjobs=([0-9a-f.]+)/.exec(location.hash || "");
    return m ? m[1].split(".").filter(function (x) { return /^[0-9a-f]{6,16}$/.test(x); }).slice(0, MAX_LIST) : [];
  }

  function draw(data) {
    var jobs = (data.jobs || []).map(function (j) {
      j.workplaces = j.workplaces || [];
      j.eases = j.eases || [];
      j.hoursKey = j.hours || "Not stated";
      return j;
    });
    var byId = {}; jobs.forEach(function (j) { if (j.id) byId[j.id] = j; });
    var byUrl = {}; jobs.forEach(function (j) { byUrl[j.url] = j; });
    var hasEase = jobs.some(function (j) { return j.eases.length; });
    var typeList = tally(jobs, function (j) { return [j.type]; });
    var placeList = tally(jobs, function (j) { return j.workplaces; });
    var cities = {}; jobs.forEach(function (j) { cities[j.city] = (cities[j.city] || 0) + 1; });
    var cityList = Object.keys(cities).sort(function (a, b) { return cities[b] - cities[a]; });
    var upd = data.updated ? new Date(data.updated) : null;

    var st = {
      q: "", city: opt.city || "All", shown: 15,
      type: list(opt.type),
      place: list(opt.workplace || OLD_INDUSTRY[opt.industry] || opt.industry),
      hours: list(opt.hours), ease: [],
      shared: hashIds(),      // a list someone picked, opened from a link
      picking: false, picked: [], qrOpen: false, copied: false, linkShown: false,
      ask: null, answered: {}  // "Was this job still open?"
    };
    if (st.shared.length) signal("shortlist", { act: "open", n: st.shared.length });

    function tally(arr, get) {
      var c = {}; arr.forEach(function (j) { get(j).forEach(function (v) { if (v) c[v] = (c[v] || 0) + 1; }); });
      return Object.keys(c).sort(function (a, b) { return (a === "Other") - (b === "Other") || c[b] - c[a]; });
    }
    var $ = function (s) { return root.querySelector(s); };

    function build() {
      root.setAttribute("aria-label", opt.title || t("title"));
      root.setAttribute("lang", lang);
      root.innerHTML =
        '<div class="lchj-head"><h2 class="lchj-h"></h2><div class="lchj-meta"><span class="lchj-count" aria-live="polite"></span>' +
        '<button type="button" class="lchj-link lchj-lang" aria-label="' + esc(t("langLabel")) + '" lang="' + (lang === "es" ? "en" : "es") + '">' + esc(t("lang")) + "</button>" +
        '<button type="button" class="lchj-link lchj-make">' + esc(t("makeList")) + "</button></div></div>" +
        '<div class="lchj-banner" hidden></div>' +
        '<div class="lchj-filters">' +
        '<div class="lchj-controls"><input type="search" class="lchj-q" placeholder="' + esc(t("search")) + '" aria-label="' + esc(t("searchLabel")) + '"><select class="lchj-city" aria-label="' + esc(t("town")) + '"></select></div>' +
        '<div class="lchj-group"><span class="lchj-label">' + esc(t("what")) + "<small>" + esc(t("pick")) + '</small></span><div class="lchj-chips" data-g="type" role="group" aria-label="' + esc(t("what")) + '"></div></div>' +
        '<div class="lchj-group"><span class="lchj-label">' + esc(t("where")) + "<small>" + esc(t("pick")) + '</small></span><div class="lchj-chips" data-g="place" role="group" aria-label="' + esc(t("where")) + '"></div></div>' +
        '<div class="lchj-group"><span class="lchj-label">' + esc(t("hours")) + '</span><div class="lchj-chips" data-g="hours" role="group" aria-label="' + esc(t("hours")) + '"></div></div>' +
        (hasEase ? '<div class="lchj-group"><span class="lchj-label">' + esc(t("ease")) + "<small>" + esc(t("easeHint")) + '</small></span><div class="lchj-chips" data-g="ease" role="group" aria-label="' + esc(t("ease")) + '"></div></div>' : "") +
        '<div class="lchj-active" hidden><span class="lchj-sum"></span><button type="button" class="lchj-clear">' + esc(t("clear")) + "</button></div></div>" +
        '<ul class="lchj-jobs"></ul><button type="button" class="lchj-more">' + esc(t("more")) + "</button>" +
        '<div class="lchj-tray" hidden></div>' +
        '<p class="lchj-foot"></p>';
      $(".lchj-h").textContent = opt.title || t("title");
      $(".lchj-filters").style.cssText = "display:flex;flex-direction:column;gap:12px";
      $(".lchj-q").value = st.q;
      cityOptions();
      $(".lchj-foot").innerHTML = t("foot")(upd && !isNaN(upd) ? esc(upd.toLocaleDateString(lang === "es" ? "es-US" : "en-US", { month: "short", day: "numeric", year: "numeric" })) : "");
      $(".lchj-q").addEventListener("input", function (e) { st.q = e.target.value; refresh(); });
      $(".lchj-city").addEventListener("change", function (e) { st.city = e.target.value; refresh(); });
      refresh();
    }
    function cityOptions() {
      $(".lchj-city").innerHTML = '<option value="All">' + esc(t("allTowns")) + "</option>" + cityList.map(function (c) { return "<option" + (c === st.city ? " selected" : "") + ">" + esc(c) + "</option>"; }).join("");
    }
    function match(j, skip) {
      var q = st.q.trim().toLowerCase();
      return (skip === "type" || !st.type.length || st.type.indexOf(j.type) > -1) &&
        (skip === "place" || !st.place.length || j.workplaces.some(function (w) { return st.place.indexOf(w) > -1; })) &&
        (skip === "hours" || !st.hours.length || st.hours.indexOf(j.hoursKey) > -1) &&
        (skip === "ease" || st.ease.every(function (e) { return j.eases.indexOf(e) > -1; })) &&
        (st.city === "All" || j.city === st.city) &&
        (!q || (j.title + " " + j.employer + " " + j.snippet).toLowerCase().indexOf(q) > -1);
    }
    function group(g, values, get, label, all) {
      var box = $('.lchj-chips[data-g="' + g + '"]');
      if (!box) return;
      var pool = jobs.filter(function (j) { return match(j, g); });
      box.innerHTML = values.map(function (v) {
        var on = st[g].indexOf(v) > -1;
        // "Fewer barriers" chips narrow together (all must apply); the others widen (any may apply).
        var need = all ? st[g].concat(on ? [] : [v]) : [v];
        var n = pool.filter(function (j) { var have = get(j); return all ? need.every(function (x) { return have.indexOf(x) > -1; }) : have.indexOf(v) > -1; }).length;
        var tip = g === "ease" ? ' title="' + esc(EASE_TIP[lang][v]) + '"' : "";
        return '<button type="button" class="lchj-chip" data-g="' + g + '" data-v="' + esc(v) + '" aria-pressed="' + on + '"' + tip + (!n && !on ? " disabled" : "") + ">" + esc(label(v)) + '<span class="n">' + n + "</span></button>";
      }).join("");
    }
    function chips() {
      group("type", typeList, function (j) { return [j.type]; }, V);
      group("place", placeList, function (j) { return j.workplaces; }, V);
      group("hours", HOURS, function (j) { return [j.hoursKey]; }, V);
      group("ease", EASE, function (j) { return j.eases; }, function (v) { return EASE_LABEL[lang][v]; }, true);
      var parts = [];
      if (st.q.trim()) parts.push('"' + st.q.trim() + '"');
      if (st.city !== "All") parts.push(st.city);
      [st.type, st.place, st.hours].forEach(function (a) { if (a.length) parts.push(a.map(V).join(t("or"))); });
      if (st.ease.length) parts.push(st.ease.map(function (v) { return EASE_LABEL[lang][v]; }).join(t("and")));
      $(".lchj-active").hidden = !parts.length;
      $(".lchj-sum").textContent = parts.length ? t("showing") + parts.join(" · ") : "";
    }
    function card(j) {
      var who = (j.employer ? "<b>" + esc(j.employer) + "</b>" : '<span class="none">' + esc(t("noEmp")) + "</span>") +
        (j.city && j.city !== j.employer ? " · " + esc(j.city) : "") + (j.hours ? " · " + esc(V(j.hours)) : "");
      var pay = j.pay ? '<div class="lchj-pay">' + esc(t("pay")) + esc(payText(j.pay)) + "</div>" :
        (j.typical_pay ? '<div class="lchj-pay typ">' + esc(t("noPay")) + esc(payText(j.typical_pay)) + "</div>" : "");
      var via = viaText(j.apply_via || "");
      var on = st.picked.indexOf(j.id) > -1;
      var pick = st.picking && j.id ? '<label class="lchj-pick"><input type="checkbox" data-pick="' + esc(j.id) + '"' + (on ? " checked" : "") +
        (!on && st.picked.length >= MAX_LIST ? " disabled" : "") + "> " + esc(t("addToList")) + "</label>" : "";
      var ask = "";
      if (st.ask === j.id) {
        ask = st.answered[j.id] ? '<div class="lchj-ask done" role="status">' + esc(t("thanks")) + "</div>" :
          '<div class="lchj-ask" role="group" aria-label="' + esc(t("ask")) + '">' + esc(t("ask")) +
          ' <button type="button" data-ask="yes">' + esc(t("yes")) + '</button><button type="button" data-ask="no">' + esc(t("no")) + "</button></div>";
      }
      return '<li class="lchj-job' + (on && st.picking ? " on" : "") + '" data-id="' + esc(j.id || "") + '">' + pick +
        '<a class="lchj-t" href="' + esc(j.url) + '" target="_blank" rel="noopener">' + esc(j.title) + "</a>" +
        '<div class="lchj-who">' + who + "</div>" + pay +
        (j.snippet ? '<div class="lchj-snip">' + esc(j.snippet) + "…</div>" : "") +
        '<div class="lchj-act"><a class="lchj-apply" href="' + esc(j.url) + '" target="_blank" rel="noopener" aria-label="' + esc(t("apply")) + ": " + esc(j.title) + '">' + esc(t("apply")) + "</a>" +
        (via ? '<span class="lchj-via">' + esc(via) + "</span>" : "") +
        '<span class="lchj-when">' + esc(t("when")(j.days, j.dated)) + "</span></div>" + ask + "</li>";
    }
    function shareLink() {
      return location.href.split("#")[0] + "#hotjobs=" + st.picked.join(".");
    }
    function tray() {
      var tr = $(".lchj-tray");
      tr.hidden = !st.picking;
      if (!st.picking) return;
      var n = st.picked.length, dis = n ? "" : " disabled";
      tr.innerHTML = '<span class="lchj-hint">' + esc(t("listHint")) + "</span>" +
        "<b>" + esc(t("picked")(n)) + "</b>" +
        '<button type="button" data-tray="copy"' + dis + ">" + esc(st.copied ? t("copied") : t("copy")) + "</button>" +
        '<button type="button" data-tray="qr"' + dis + ">" + esc(t("qr")) + "</button>" +
        '<button type="button" data-tray="print"' + dis + ">" + esc(t("print")) + "</button>" +
        '<button type="button" class="alt" data-tray="done">' + esc(t("done")) + "</button>" +
        (st.linkShown && n ? '<label style="flex-basis:100%;display:flex;gap:8px;align-items:center;font-size:12px">' + esc(t("copyHere")) + ' <input type="text" readonly value="' + esc(shareLink()) + '"></label>' : "") +
        (st.qrOpen && n ? '<div class="lchj-qr"><div class="lchj-qrbox"></div><span>' + esc(t("scan")) + "</span></div>" : "");
      if (st.qrOpen && n) qrInto(tr.querySelector(".lchj-qrbox"), shareLink());
      var inp = tr.querySelector("input[readonly]");
      if (inp) { inp.focus(); inp.select(); }
    }
    function render() {
      var f;
      var banner = $(".lchj-banner");
      if (st.shared.length) {
        f = st.shared.map(function (id) { return byId[id]; }).filter(Boolean);
        var goneN = st.shared.length - f.length;
        banner.hidden = false;
        banner.innerHTML = "<span><b>" + esc(t("listFor")(st.shared.length)) + "</b>" + (goneN ? " " + esc(t("gone")(goneN)) : "") + "</span>" +
          '<button type="button" class="lchj-ghost" data-showall="1">' + esc(t("showAll")) + "</button>";
        $(".lchj-filters").hidden = true;
        $(".lchj-make").hidden = true;
        $(".lchj-count").textContent = "";
      } else {
        f = jobs.filter(function (j) { return match(j); });
        banner.hidden = true;
        $(".lchj-filters").hidden = false;
        $(".lchj-make").hidden = false;
        $(".lchj-count").textContent = t("count")(f.length, jobs.length);
      }
      $(".lchj-jobs").innerHTML = f.length ? f.slice(0, st.shared.length ? MAX_LIST : st.shown).map(card).join("") :
        '<li class="lchj-empty">' + esc(t("none")) + ' <button type="button" class="lchj-clear">' + esc(t("clearLower")) + "</button>.</li>";
      $(".lchj-more").hidden = !!st.shared.length || f.length <= st.shown;
      tray();
    }
    function refresh() { st.shown = 15; chips(); render(); }

    // ---- QR code and printable sheet ------------------------------------------------------------------
    var qrLoading = null;
    function loadQR() {
      if (window.QRCode) return Promise.resolve();
      if (!qrLoading) qrLoading = new Promise(function (ok, bad) {
        var s = document.createElement("script"); s.src = QR_LIB; s.onload = ok; s.onerror = bad; document.head.appendChild(s);
      });
      return qrLoading;
    }
    function qrInto(box, text) {
      return loadQR().then(function () {
        box.innerHTML = "";
        new window.QRCode(box, { text: text, width: 180, height: 180, correctLevel: window.QRCode.CorrectLevel.M });
      }).catch(function () { box.textContent = text; });
    }
    function printSheet() {
      var w = window.open("", "_blank");
      if (!w) return;
      var link = shareLink(), picked = st.picked.map(function (id) { return byId[id]; }).filter(Boolean);
      var rows = picked.map(function (j) {
        var pay = j.pay ? t("pay") + payText(j.pay) : (j.typical_pay ? t("noPay") + payText(j.typical_pay) : "");
        return '<li><h2>' + esc(j.title) + "</h2><p>" + esc([j.employer || t("noEmp"), j.city, j.hours ? V(j.hours) : ""].filter(Boolean).join(" · ")) + "</p>" +
          (pay ? "<p>" + esc(pay) + "</p>" : "") + '<p class="u">' + esc(t("applyAt")) + " " + esc(j.url) + "</p></li>";
      }).join("");
      w.document.write('<!doctype html><html lang="' + lang + '"><head><meta charset="utf-8"><title>' + esc(t("sheetTitle")) + "</title><style>" +
        "body{font:14px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif;color:#111;margin:32px;max-width:720px}" +
        "h1{font-size:22px;margin:0 0 4px}.sub{color:#555;margin:0 0 16px}ol{padding-left:20px}li{margin:0 0 14px;break-inside:avoid}" +
        "h2{font-size:16px;margin:0}p{margin:2px 0}.u{font-size:11px;color:#444;word-break:break-all}" +
        ".qr{display:flex;gap:16px;align-items:center;border-top:1px solid #ccc;padding-top:14px;margin-top:8px}.qr img,.qr canvas{width:140px;height:140px}" +
        "</style></head><body><h1>" + esc(t("sheetTitle")) + '</h1><p class="sub">' + esc(opt.title || t("title")) + " · " + esc(new Date().toLocaleDateString(lang === "es" ? "es-US" : "en-US")) + "</p><ol>" + rows +
        '</ol><div class="qr"><div id="q"></div><div><b>' + esc(t("scan")) + '</b><p class="u">' + esc(link) + "</p><p>" + esc(t("daily")) + "</p></div></div></body></html>");
      w.document.close();
      var box = w.document.getElementById("q");
      loadQR().then(function () {
        new window.QRCode(box, { text: link, width: 140, height: 140, correctLevel: window.QRCode.CorrectLevel.M });
      }).catch(function () {}).then(function () { setTimeout(function () { w.focus(); w.print(); }, 300); });
    }
    function copyLink() {
      var link = shareLink();
      var done = function () { st.copied = true; st.linkShown = false; tray(); setTimeout(function () { st.copied = false; if (st.picking) tray(); }, 2500); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(done, function () { st.linkShown = true; tray(); });
      } else { st.linkShown = true; tray(); }
    }

    // ---- Events ---------------------------------------------------------------------------------------
    root.addEventListener("change", function (e) {
      var c = e.target;
      if (!c.dataset || !c.dataset.pick) return;
      var id = c.dataset.pick, i = st.picked.indexOf(id);
      if (c.checked && i < 0 && st.picked.length < MAX_LIST) st.picked.push(id);
      if (!c.checked && i > -1) st.picked.splice(i, 1);
      st.qrOpen = false; st.linkShown = false;
      render();
    });
    root.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button");
      if (!b || !root.contains(b) || b.disabled) return;
      if (b.dataset.g) {
        var a = st[b.dataset.g], i = a.indexOf(b.dataset.v);
        if (i > -1) a.splice(i, 1); else a.push(b.dataset.v);
      } else if (b.classList.contains("lchj-clear")) {
        st.q = ""; st.city = "All"; st.type = []; st.place = []; st.hours = []; st.ease = [];
        $(".lchj-q").value = ""; cityOptions();
      } else if (b.classList.contains("lchj-more")) { st.shown += 15; render(); return; }
      else if (b.classList.contains("lchj-lang")) {
        lang = lang === "es" ? "en" : "es"; store("lchj-lang", lang); build(); $(".lchj-lang").focus(); return;
      } else if (b.classList.contains("lchj-make")) {
        st.picking = !st.picking; render(); return;
      } else if (b.dataset.showall) {
        st.shared = [];
        try { history.replaceState(null, "", location.href.split("#")[0]); } catch (x) { /* ignore */ }
      } else if (b.dataset.tray) {
        var act = b.dataset.tray;
        if (act === "done") { st.picking = false; st.qrOpen = false; st.linkShown = false; render(); return; }
        if (act === "copy") copyLink();
        if (act === "qr") { st.qrOpen = !st.qrOpen; tray(); }
        if (act === "print") printSheet();
        signal("shortlist", { act: act, n: st.picked.length });
        return;
      } else if (b.dataset.ask) {
        var j = byId[st.ask] || {};
        st.answered[st.ask] = true;
        signal("stillopen", { id: st.ask, a: b.dataset.ask, emp: j.employer || "" });
        render(); return;
      } else return;
      refresh();
    });
    build();

    // ---- "Was this job still open?" -------------------------------------------------------------------
    // Shown only on the listing someone just opened, and only if they come back within two minutes.
    var opened = null;
    root.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a.lchj-apply, a.lchj-t");
      if (!a || !root.contains(a)) return;
      var j = byUrl[a.getAttribute("href")] || {};
      signal("apply", { emp: j.employer || "Employer not listed", t: j.type || "" });
      if (j.id) opened = { id: j.id, at: Date.now() };
    });
    function back() {
      if (document.visibilityState === "hidden" || !opened) return;
      var gap = Date.now() - opened.at, id = opened.id;
      if (gap < 2000) return;  // the new tab has not really been used yet
      opened = null;
      if (gap > 120000 || st.answered[id] || st.ask === id) return;
      signal("quickreturn", { id: id });
      st.ask = id;
      render();
    }
    document.addEventListener("visibilitychange", back);
    window.addEventListener("focus", back);

    signal("load");
    if ("IntersectionObserver" in window) {
      // Counted as seen once 200px of it (or half, if it is shorter) is on screen. A share-of-widget threshold
      // never trips on a phone, because the full job list is several screens tall.
      var seen = new IntersectionObserver(function (entries) {
        if (entries.some(function (x) {
          return x.isIntersecting && x.intersectionRect.height >= Math.min(200, x.boundingClientRect.height / 2);
        })) { signal("view"); seen.disconnect(); }
      }, { threshold: [0, 0.02, 0.05, 0.1, 0.2, 0.4] });
      seen.observe(root);
    }
  }
})();
