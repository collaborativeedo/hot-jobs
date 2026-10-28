/*!
 * Lane County Hot Jobs widget
 * Embed on any site with one line:
 *   <script src="https://YOUR-HOST/widget.js" defer></script>
 * Optional settings on the same tag:
 *   data-type="Healthcare & human services"   start filtered to a type of work ("A|B" for several)
 *   data-workplace="Healthcare"               start filtered to a kind of workplace ("A|B" for several)
 *   data-hours="Full-time"                    start filtered to Full-time, Part-time or Temporary or seasonal
 *   data-city="Florence"                      start filtered to one city
 *   data-title="Open healthcare jobs"         heading text
 *   data-target="my-div-id"                   draw inside an existing element
 * The widget reads jobs.json from the same folder as this file, so updating
 * that file updates every site that embeds the widget.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  if (!me) return;
  var base = me.src.replace(/[^\/]*$/, "");
  var opt = me.dataset || {};

  var CSS = [
    ".lchj{--a:#0f5c4d;--as:#dcebe6;--ink:#16231f;--mu:#56655f;--ln:#d3dbd7;--sk:#eef2f0;box-sizing:border-box;max-width:900px;margin:24px auto;padding:16px;border:1px solid var(--ln);border-radius:10px;background:#fff;color:var(--ink);font-size:15px;line-height:1.5;display:flex;flex-direction:column;gap:12px;text-align:left}",
    ".lchj *{box-sizing:border-box}",
    ".lchj [hidden]{display:none!important}",
    ".lchj .lchj-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px}",
    ".lchj h2.lchj-h{margin:0;padding:0;font-size:22px;line-height:1.2;color:var(--ink);border:0;text-transform:none;letter-spacing:0}",
    ".lchj .lchj-count{font-size:13px;color:var(--mu)}",
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
    ".lchj .lchj-active{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px;color:var(--mu);background:var(--sk);border-radius:8px;padding:6px 10px}",
    ".lchj button.lchj-clear{font:inherit;font-size:13px;font-weight:600;border:1px solid var(--a);background:#fff;color:var(--a);border-radius:999px;padding:3px 12px;margin:0 0 0 auto;cursor:pointer;width:auto;text-transform:none;box-shadow:none}",
    ".lchj button:focus-visible,.lchj input:focus-visible,.lchj select:focus-visible,.lchj a:focus-visible{outline:2px solid var(--a);outline-offset:2px}",
    ".lchj ul.lchj-jobs{list-style:none;margin:0;padding:0}",
    ".lchj li.lchj-job{display:flex;flex-direction:column;gap:3px;padding:14px 2px;margin:0;border-top:1px solid var(--ln);list-style:none}",
    ".lchj li.lchj-job::before{content:none}",
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
    ".lchj .lchj-empty{padding:20px 0;color:var(--mu)}",
    ".lchj button.lchj-more{align-self:center;font:inherit;font-size:14px;font-weight:600;border:1px solid var(--a);color:var(--a);background:#fff;border-radius:8px;padding:8px 16px;cursor:pointer;width:auto;text-transform:none}",
    ".lchj .lchj-foot{font-size:12px;color:var(--mu);border-top:1px solid var(--ln);padding-top:10px;margin:0}",
    ".lchj .lchj-foot a{color:var(--a)}",
    "@media (max-width:520px){.lchj .lchj-controls{grid-template-columns:1fr}.lchj{padding:12px}.lchj .lchj-when{margin-left:0}}"
  ].join("\n");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
    });
  }
  function when(d, dated) {
    var w = d <= 0 ? "today" : d === 1 ? "1 day ago" : d + " days ago";
    return dated === false ? "Added " + w : w.charAt(0).toUpperCase() + w.slice(1);
  }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }

  if (!document.getElementById("lchj-style")) {
    var st = document.createElement("style");
    st.id = "lchj-style";
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  var root = el("div", "lchj");
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", "Open jobs in Lane County");
  var target = opt.target && document.getElementById(opt.target);
  if (target) target.appendChild(root); else me.parentNode.insertBefore(root, me.nextSibling);
  root.innerHTML = '<div class="lchj-head"><h2 class="lchj-h"></h2><span class="lchj-count">Loading jobs…</span></div>';
  root.querySelector(".lchj-h").textContent = opt.title || "Open jobs in Lane County";

  fetch(base + "jobs.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () {
      root.querySelector(".lchj-count").textContent = "";
      root.appendChild(el("p", "lchj-empty", 'Job listings are not available right now. Try the <a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">QualityInfo Job Finder</a>.'));
    });

  var OLD_INDUSTRY = { "Public sector": "Government", "Nonprofit": "Nonprofit & social services" };
  var HOURS = ["Full-time", "Part-time", "Temporary or seasonal", "Not stated"];
  function list(v) { return v ? String(v).split("|").map(function (x) { return x.trim(); }).filter(Boolean) : []; }

  function draw(data) {
    var jobs = (data.jobs || []).map(function (j) {
      j.workplaces = j.workplaces || [];
      j.hoursKey = j.hours || "Not stated";
      return j;
    });
    var typeList = tally(jobs, function (j) { return [j.type]; });
    var placeList = tally(jobs, function (j) { return j.workplaces; });
    var cities = {}; jobs.forEach(function (j) { cities[j.city] = (cities[j.city] || 0) + 1; });
    var cityList = Object.keys(cities).sort(function (a, b) { return cities[b] - cities[a]; });

    var st = {
      q: "", city: opt.city || "All", shown: 15,
      type: list(opt.type),
      place: list(opt.workplace || OLD_INDUSTRY[opt.industry] || opt.industry),
      hours: list(opt.hours)
    };

    root.innerHTML =
      '<div class="lchj-head"><h2 class="lchj-h"></h2><span class="lchj-count"></span></div>' +
      '<div class="lchj-controls"><input type="search" class="lchj-q" placeholder="Search jobs or employers, e.g. nurse, CDL, PeaceHealth" aria-label="Search jobs or employers"><select class="lchj-city" aria-label="Town"></select></div>' +
      '<div class="lchj-group"><span class="lchj-label">What you do<small>pick one or more</small></span><div class="lchj-chips" data-g="type" role="group" aria-label="What you do"></div></div>' +
      '<div class="lchj-group"><span class="lchj-label">Where you\'d work<small>pick one or more</small></span><div class="lchj-chips" data-g="place" role="group" aria-label="Where you would work"></div></div>' +
      '<div class="lchj-group"><span class="lchj-label">Hours</span><div class="lchj-chips" data-g="hours" role="group" aria-label="Hours"></div></div>' +
      '<div class="lchj-active" hidden><span class="lchj-sum"></span><button type="button" class="lchj-clear">Clear all filters</button></div>' +
      '<ul class="lchj-jobs"></ul><button type="button" class="lchj-more">Show more jobs</button>' +
      '<p class="lchj-foot"></p>';
    var $ = function (s) { return root.querySelector(s); };
    $(".lchj-h").textContent = opt.title || "Open jobs in Lane County";
    function cityOptions() {
      $(".lchj-city").innerHTML = '<option value="All">All Lane County</option>' + cityList.map(function (c) { return "<option" + (c === st.city ? " selected" : "") + ">" + esc(c) + "</option>"; }).join("");
    }
    cityOptions();
    var upd = data.updated ? new Date(data.updated) : null;
    $(".lchj-foot").innerHTML = "Jobs from the Oregon Employment Department's " + '<a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">QualityInfo Job Finder</a> and employers\' own hiring sites' +
      (upd && !isNaN(upd) ? ". Updated " + esc(upd.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })) : "") +
      ". Average pay figures come from Oregon Employment Department wage data for the occupation, not from the posting. Not every opening is posted online. This is a pilot.";

    function tally(arr, get) {
      var c = {}; arr.forEach(function (j) { get(j).forEach(function (v) { if (v) c[v] = (c[v] || 0) + 1; }); });
      return Object.keys(c).sort(function (a, b) { return (a === "Other") - (b === "Other") || c[b] - c[a]; });
    }
    function match(j, skip) {
      var q = st.q.trim().toLowerCase();
      return (skip === "type" || !st.type.length || st.type.indexOf(j.type) > -1) &&
        (skip === "place" || !st.place.length || j.workplaces.some(function (w) { return st.place.indexOf(w) > -1; })) &&
        (skip === "hours" || !st.hours.length || st.hours.indexOf(j.hoursKey) > -1) &&
        (st.city === "All" || j.city === st.city) &&
        (!q || (j.title + " " + j.employer + " " + j.snippet).toLowerCase().indexOf(q) > -1);
    }
    function group(g, values, get) {
      var pool = jobs.filter(function (j) { return match(j, g); });
      $('.lchj-chips[data-g="' + g + '"]').innerHTML = values.map(function (v) {
        var n = pool.filter(function (j) { return get(j).indexOf(v) > -1; }).length;
        var on = st[g].indexOf(v) > -1;
        return '<button type="button" class="lchj-chip" data-g="' + g + '" data-v="' + esc(v) + '" aria-pressed="' + on + '"' + (!n && !on ? " disabled" : "") + ">" + esc(v) + '<span class="n">' + n + "</span></button>";
      }).join("");
    }
    function chips() {
      group("type", typeList, function (j) { return [j.type]; });
      group("place", placeList, function (j) { return j.workplaces; });
      group("hours", HOURS, function (j) { return [j.hoursKey]; });
      var parts = [];
      if (st.q.trim()) parts.push('"' + st.q.trim() + '"');
      if (st.city !== "All") parts.push(st.city);
      [st.type, st.place, st.hours].forEach(function (a) { if (a.length) parts.push(a.join(" or ")); });
      $(".lchj-active").hidden = !parts.length;
      $(".lchj-sum").textContent = parts.length ? "Showing: " + parts.join(" · ") : "";
    }
    function card(j) {
      var who = (j.employer ? "<b>" + esc(j.employer) + "</b>" : '<span class="none">Employer not listed</span>') +
        (j.city && j.city !== j.employer ? " · " + esc(j.city) : "") + (j.hours ? " · " + esc(j.hours) : "");
      var pay = j.pay ? '<div class="lchj-pay">Pay: ' + esc(j.pay) + "</div>" :
        (j.typical_pay ? '<div class="lchj-pay typ">Pay not listed. ' + esc(j.typical_pay) + "</div>" : "");
      var via = j.apply_via || "";
      return '<li class="lchj-job"><a class="lchj-t" href="' + esc(j.url) + '" target="_blank" rel="noopener">' + esc(j.title) + "</a>" +
        '<div class="lchj-who">' + who + "</div>" + pay +
        (j.snippet ? '<div class="lchj-snip">' + esc(j.snippet) + "…</div>" : "") +
        '<div class="lchj-act"><a class="lchj-apply" href="' + esc(j.url) + '" target="_blank" rel="noopener" aria-label="View and apply: ' + esc(j.title) + '">View and apply</a>' +
        (via ? '<span class="lchj-via">' + esc(via) + "</span>" : "") +
        '<span class="lchj-when">' + when(j.days, j.dated) + "</span></div></li>";
    }
    function render() {
      var f = jobs.filter(function (j) { return match(j); });
      $(".lchj-count").textContent = f.length + " of " + jobs.length + " openings";
      $(".lchj-jobs").innerHTML = f.length ? f.slice(0, st.shown).map(card).join("") :
        '<li class="lchj-empty">No openings match. Try fewer filters or <button type="button" class="lchj-clear" style="margin:0">clear all filters</button>.</li>';
      $(".lchj-more").hidden = f.length <= st.shown;
    }
    function refresh() { st.shown = 15; chips(); render(); }
    root.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button");
      if (!b || !root.contains(b) || b.disabled) return;
      if (b.dataset.g) {
        var a = st[b.dataset.g], i = a.indexOf(b.dataset.v);
        if (i > -1) a.splice(i, 1); else a.push(b.dataset.v);
      } else if (b.classList.contains("lchj-clear")) {
        st.q = ""; st.city = "All"; st.type = []; st.place = []; st.hours = [];
        $(".lchj-q").value = ""; cityOptions();
      } else if (b.classList.contains("lchj-more")) { st.shown += 15; render(); return; }
      else return;
      refresh();
    });
    $(".lchj-q").addEventListener("input", function (e) { st.q = e.target.value; refresh(); });
    $(".lchj-city").addEventListener("change", function (e) { st.city = e.target.value; refresh(); });
    refresh();
  }
})();
