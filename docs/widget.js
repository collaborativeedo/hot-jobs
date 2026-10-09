/*!
 * Lane County Hot Jobs widget
 * Embed on any site with one line:
 *   <script src="https://YOUR-HOST/widget.js" defer></script>
 * Optional settings on the same tag:
 *   data-type="Healthcare & human services"   start filtered to one type of work
 *   data-industry="Wood products & forestry"  start filtered to one industry
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
    ".lchj{--a:#0f5c4d;--as:#dcebe6;--h:#a85a0c;--hs:#fbead6;--ink:#16231f;--mu:#56655f;--ln:#d3dbd7;--sk:#eef2f0;box-sizing:border-box;max-width:900px;margin:24px auto;padding:16px;border:1px solid var(--ln);border-radius:10px;background:#fff;color:var(--ink);font-size:15px;line-height:1.5;display:flex;flex-direction:column;gap:12px;text-align:left}",
    ".lchj *{box-sizing:border-box}",
    ".lchj [hidden]{display:none!important}",
    ".lchj .lchj-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px}",
    ".lchj h2.lchj-h{margin:0;padding:0;font-size:22px;line-height:1.2;color:var(--ink);border:0;text-transform:none;letter-spacing:0}",
    ".lchj .lchj-count{font-size:13px;color:var(--mu)}",
    ".lchj .lchj-controls{display:grid;grid-template-columns:1fr auto;gap:8px}",
    ".lchj input[type=search],.lchj select{font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--ln);border-radius:8px;background:#fff;color:var(--ink);min-width:0;width:100%;margin:0;height:auto;box-shadow:none}",
    ".lchj .lchj-group{display:flex;flex-direction:column;gap:6px}",
    ".lchj .lchj-label{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mu)}",
    ".lchj .lchj-chips{display:flex;flex-wrap:wrap;gap:6px}",
    ".lchj button.lchj-chip{font:inherit;font-size:13px;font-weight:500;border:1px solid var(--ln);background:#fff;color:var(--ink);border-radius:999px;padding:4px 10px;margin:0;cursor:pointer;line-height:1.4;text-transform:none;letter-spacing:0;box-shadow:none;min-height:0;width:auto}",
    ".lchj button.lchj-chip .n{font-size:11px;color:var(--mu);margin-left:4px}",
    ".lchj button.lchj-chip[aria-pressed=true]{background:var(--a);border-color:var(--a);color:#fff}",
    ".lchj button.lchj-chip[aria-pressed=true] .n{color:#fff;opacity:.8}",
    ".lchj button.lchj-chip:disabled{opacity:.45;cursor:default}",
    ".lchj button:focus-visible,.lchj input:focus-visible,.lchj select:focus-visible,.lchj a:focus-visible{outline:2px solid var(--a);outline-offset:2px}",
    ".lchj ul.lchj-jobs{list-style:none;margin:0;padding:0}",
    ".lchj li.lchj-job{display:grid;grid-template-columns:1fr auto;gap:2px 12px;padding:12px 2px;margin:0;border-top:1px solid var(--ln);list-style:none}",
    ".lchj li.lchj-job::before{content:none}",
    ".lchj a.lchj-t{font-weight:600;color:var(--ink);text-decoration:none;min-width:0}",
    ".lchj a.lchj-t:hover{color:var(--a);text-decoration:underline}",
    ".lchj .lchj-when{font-size:12px;color:var(--mu);text-align:right;white-space:nowrap}",
    ".lchj .lchj-sub{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 10px;font-size:13px;color:var(--mu);align-items:center}",
    ".lchj .lchj-snip{grid-column:1/-1;font-size:13px;color:var(--mu);overflow-wrap:anywhere}",
    ".lchj .lchj-tag{font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;background:var(--as);color:var(--a)}",
    ".lchj .lchj-tag.rural{background:var(--hs);color:var(--h)}",
    ".lchj .lchj-tag.ind{background:var(--sk);color:var(--ink)}",
    ".lchj .lchj-empty{padding:20px 0;color:var(--mu)}",
    ".lchj button.lchj-more{align-self:center;font:inherit;font-size:14px;font-weight:600;border:1px solid var(--a);color:var(--a);background:#fff;border-radius:8px;padding:8px 16px;cursor:pointer;width:auto;text-transform:none}",
    ".lchj .lchj-foot{font-size:12px;color:var(--mu);border-top:1px solid var(--ln);padding-top:10px;margin:0}",
    ".lchj .lchj-foot a{color:var(--a)}",
    "@media (max-width:520px){.lchj .lchj-controls{grid-template-columns:1fr}.lchj{padding:12px}}"
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
  function soc(s) { return s && s.length === 6 ? "SOC " + s.slice(0, 2) + "-" + s.slice(2) : ""; }
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

  function draw(data) {
    var jobs = data.jobs || [];
    var count = function (key, val) { return jobs.filter(function (j) { return key === "type" ? j.type === val : (j.industries || []).indexOf(val) > -1; }).length; };
    var types = {}; jobs.forEach(function (j) { types[j.type] = (types[j.type] || 0) + 1; });
    var typeList = Object.keys(types).sort(function (a, b) { return (a === "Other") - (b === "Other") || types[b] - types[a]; });
    var INDS = ["Wood products & forestry", "Food & beverage", "Bioscience", "Public sector", "Nonprofit"];
    var cities = {}; jobs.forEach(function (j) { cities[j.city] = (cities[j.city] || 0) + 1; });
    var cityList = Object.keys(cities).sort(function (a, b) { return cities[b] - cities[a]; });

    var st = { q: "", type: opt.type || "All", ind: opt.industry || "All", city: opt.city || "All", shown: 15 };

    root.innerHTML =
      '<div class="lchj-head"><h2 class="lchj-h"></h2><span class="lchj-count"></span></div>' +
      '<div class="lchj-controls"><input type="search" class="lchj-q" placeholder="Search job titles, e.g. nurse, CDL, welder" aria-label="Search job titles"><select class="lchj-city" aria-label="City"></select></div>' +
      '<div class="lchj-group"><span class="lchj-label">Type of work</span><div class="lchj-chips lchj-types" role="group" aria-label="Filter by type of work"></div></div>' +
      '<div class="lchj-group"><span class="lchj-label">Industry</span><div class="lchj-chips lchj-inds" role="group" aria-label="Filter by industry"></div></div>' +
      '<ul class="lchj-jobs"></ul><button type="button" class="lchj-more">Show more jobs</button>' +
      '<p class="lchj-foot"></p>';
    var $ = function (s) { return root.querySelector(s); };
    $(".lchj-h").textContent = opt.title || "Open jobs in Lane County";
    $(".lchj-city").innerHTML = '<option value="All">All Lane County</option>' + cityList.map(function (c) { return '<option' + (c === st.city ? " selected" : "") + ">" + esc(c) + "</option>"; }).join("");
    var upd = data.updated ? new Date(data.updated) : null;
    $(".lchj-foot").innerHTML = "Jobs from the " + '<a href="https://www.qualityinfo.org/jfind" target="_blank" rel="noopener">QualityInfo Job Finder</a>, Oregon Employment Department' +
      (upd && !isNaN(upd) ? ". Updated " + esc(upd.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })) : "") +
      ". Not every opening is posted online. This is a pilot.";

    function chips() {
      $(".lchj-types").innerHTML = ["All"].concat(typeList).map(function (t) {
        return '<button type="button" class="lchj-chip" data-type="' + esc(t) + '" aria-pressed="' + (st.type === t) + '">' + esc(t) + '<span class="n">' + (t === "All" ? jobs.length : types[t]) + "</span></button>";
      }).join("");
      $(".lchj-inds").innerHTML = ["All"].concat(INDS).map(function (t) {
        var n = t === "All" ? "" : count("ind", t);
        return '<button type="button" class="lchj-chip" data-ind="' + esc(t) + '" aria-pressed="' + (st.ind === t) + '"' + (t !== "All" && !n ? " disabled" : "") + ">" + esc(t === "All" ? "Any industry" : t) + '<span class="n">' + n + "</span></button>";
      }).join("");
    }
    function filtered() {
      var q = st.q.trim().toLowerCase();
      return jobs.filter(function (j) {
        return (st.type === "All" || j.type === st.type) &&
          (st.ind === "All" || (j.industries || []).indexOf(st.ind) > -1) &&
          (st.city === "All" || j.city === st.city) &&
          (!q || (j.title + " " + j.employer + " " + j.snippet).toLowerCase().indexOf(q) > -1);
      });
    }
    function render() {
      var f = filtered();
      $(".lchj-count").textContent = f.length + " of " + jobs.length + " openings";
      $(".lchj-jobs").innerHTML = f.length ? f.slice(0, st.shown).map(function (j) {
        return '<li class="lchj-job"><a class="lchj-t" href="' + esc(j.url) + '" target="_blank" rel="noopener">' + esc(j.title) + "</a>" +
          '<span class="lchj-when">' + when(j.days, j.dated) + "</span>" +
          '<div class="lchj-sub">' + (j.employer ? "<span>" + esc(j.employer) + "</span>" : "") + "<span>" + esc(j.city) + "</span>" +
          '<span class="lchj-tag">' + esc(j.type) + "</span>" +
          (j.industries || []).map(function (i) { return '<span class="lchj-tag ind">' + esc(i) + "</span>"; }).join("") +
          (j.rural ? '<span class="lchj-tag rural">Outside the metro</span>' : "") +
          "<span>" + esc(j.route) + "</span><span>" + soc(j.soc) + "</span></div>" +
          (j.snippet ? '<div class="lchj-snip">' + esc(j.snippet) + "…</div>" : "") + "</li>";
      }).join("") : '<li class="lchj-empty">No openings match. Try a broader search or another town.</li>';
      $(".lchj-more").hidden = f.length <= st.shown;
    }
    root.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button");
      if (!b || !root.contains(b) || b.disabled) return;
      if (b.dataset.type) st.type = b.dataset.type;
      else if (b.dataset.ind) st.ind = b.dataset.ind;
      else if (b.classList.contains("lchj-more")) { st.shown += 15; render(); return; }
      else return;
      st.shown = 15; chips(); render();
    });
    $(".lchj-q").addEventListener("input", function (e) { st.q = e.target.value; st.shown = 15; render(); });
    $(".lchj-city").addEventListener("change", function (e) { st.city = e.target.value; st.shown = 15; render(); });
    chips(); render();
  }
})();
