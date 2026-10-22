"""Build outputs/dashboard.html - a self-contained dashboard of the cleaned dataset.

Reads data/processed/eda_tools_clean.csv and writes ONE html file with the data embedded, so it opens by
double-click, works offline, and is rebuilt from the newest data on every pipeline run (it is the last step
of scripts/pipeline.py). Standard library only. Nothing is computed from outside the CSV: every number on the
page is counted in the browser from the embedded rows, and an empty field is shown as 'Not stated'.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "eda_tools_clean.csv"
OUT = ROOT / "outputs" / "dashboard.html"
KEEP = ["tool_id", "tool_name", "vendor_canonical", "category", "license_model", "license", "region",
        "country_region", "latest_release_year", "first_release_year", "supported_platforms",
        "languages_formats", "repository_url", "website_url", "source_url", "source_types", "source_count",
        "date_collected"]

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global EDA Tools Explorer</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--fg:#1d2327;--muted:#5d666d;--line:#dcdedb;--bar:#2f6f8f;--grey:#b9bdb9;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#15191c;--panel:#1d2327;--fg:#e8eaea;--muted:#9aa3a9;--line:#323a3f;--bar:#6fb1d0;--grey:#58616a;--bad:#f2837a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Segoe UI",sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:24px max(16px,env(safe-area-inset-left))}
h1{font:400 2rem/1.15 Georgia,serif;margin:0 0 4px}
.lede{color:var(--muted);margin:0 0 20px;max-width:48rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:12px;margin-bottom:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;min-width:0}
.k{color:var(--muted);font-size:12px}.big{font:400 2.2rem/1.1 Georgia,serif;font-variant-numeric:tabular-nums;margin-top:4px}
.sub{color:var(--muted);font-size:12px;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr));gap:12px;margin-bottom:12px}
h2{font-size:15px;font-weight:600;margin:0}.note{color:var(--muted);font-size:12px;margin:2px 0 12px}
svg{display:block;max-width:100%}
.t{font-size:12px;fill:var(--muted)}.v{font-size:12px;fill:var(--fg)}
.tools{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.tools input,.tools select{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;min-width:0}
.tools input{flex:1 1 14rem}
.box{max-height:34rem;overflow:auto;border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:12px}
th{position:sticky;top:0;background:var(--panel);text-align:left;border-bottom:1px solid var(--line);padding:0;white-space:nowrap}
th button{all:unset;cursor:pointer;display:block;padding:6px 8px;width:100%;box-sizing:border-box}
th button:focus-visible{outline:2px solid var(--fg);outline-offset:-2px}
td{padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top;max-width:18rem;overflow-wrap:anywhere}
td:empty::after{content:"\2013";color:var(--muted)}
a{color:var(--fg);text-underline-offset:2px}
.foot{color:var(--muted);font-size:12px;max-width:50rem}
#tip{position:fixed;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 8px;font-size:12px;white-space:nowrap;z-index:9}
</style></head><body><div class="wrap">
<h1>Global EDA Tools Explorer</h1>
<p class="lede">Every electronic design automation tool found across published lists, community lists, Wikipedia, vendor sites and GitHub, one row per tool. Snapshot collected <b id="snap"></b>. Built from the CSV on <b id="built"></b>.</p>
<div class="kpis" id="kpis"></div>
<div class="grid" id="charts"></div>
<div class="card"><h2>All tools</h2><p class="note">Search, filter and sort. A tool name links to the page it was found on.</p>
<div class="tools"><input id="q" type="search" placeholder="Search tool or vendor" aria-label="Search tool or vendor">
<select id="fc" aria-label="Category"></select><select id="fl" aria-label="Licence model"></select><select id="fr" aria-label="Region"></select></div>
<div class="box"><table><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table></div>
<p class="note" id="none" hidden>No tools match these filters.</p></div>
<p class="foot">Rows were gathered by keyword and topic rules, so some GitHub entries are designs or demos rather than tools. The completeness chart shows what each field covers; empty means no source stated it, and nothing is estimated.</p>
<div id="tip" hidden></div></div>
<script>
const D = __DATA__;
const NS = 'http://www.w3.org/2000/svg', nf = new Intl.NumberFormat('en'), pf = v => Math.round(v * 100) + '%';
const $ = id => document.getElementById(id), tip = $('tip');
const blank = v => !v || !String(v).trim();
function el(tag, attrs, text) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text !== undefined) e.textContent = text; return e; }
function showTip(ev, t) { tip.textContent = t; tip.hidden = false; tip.style.left = Math.min(ev.clientX + 12, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (ev.clientY + 14) + 'px'; }
function count(key, label, top) {
  const m = {}; D.forEach(r => { const k = blank(r[key]) ? label : r[key].trim(); if (k) m[k] = (m[k] || 0) + 1; });
  let a = Object.keys(m).map(k => [k, m[k]]).sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0]));
  return top ? a.slice(0, top) : a;
}
$('snap').textContent = D.length ? D[0].date_collected : '';
$('built').textContent = new Date().toISOString ? '__BUILT__' : '';
// headline
const n = D.length, os = D.filter(r => r.license_model === 'open-source').length, co = D.filter(r => r.license_model === 'commercial').length, mu = D.filter(r => +r.source_count >= 2).length;
[['Tools', n, 'One row per tool, duplicates merged'], ['Open source', os, pf(os / n) + ' of all tools'], ['Commercial', co, pf(co / n) + ' of all tools'], ['Listed by 2+ sources', mu, pf(mu / n) + ' of all tools']].forEach(([k, v, s]) => {
  const d = document.createElement('div'); d.className = 'card';
  [['k', k], ['big', nf.format(v)], ['sub', s]].forEach(([c, t]) => { const x = document.createElement('div'); x.className = c; x.textContent = t; d.appendChild(x); });
  $('kpis').appendChild(d);
});
// charts
function bars(rows, fmt, max, unit) {
  const W = 420, rh = 26, H = rows.length * rh + 8, svg = el('svg', { width: '100%', viewBox: `0 0 ${W} ${H}`, height: H });
  const lw = 150, rw = 54, mx = max || Math.max(...rows.map(r => r[1]), 1);
  rows.forEach(([l, v], i) => {
    const y = 4 + i * rh, w = Math.max(2, (W - lw - rw) * v / mx);
    let s = l; const t = el('text', { class: 't', x: lw - 8, y: y + 17, 'text-anchor': 'end' }, s); svg.appendChild(t);
    while (t.textContent.length > 22) t.textContent = t.textContent.slice(0, -2) + '…';
    svg.appendChild(el('rect', { x: lw, y: y + 5, width: w, height: rh - 10, rx: 4, fill: l === 'Not stated' ? 'var(--grey)' : 'var(--bar)' }));
    svg.appendChild(el('text', { class: 'v', x: lw + w + 6, y: y + 17 }, fmt(v)));
    const hit = el('rect', { x: 0, y, width: W, height: rh, fill: 'transparent' });
    hit.addEventListener('mousemove', e => showTip(e, l + ': ' + fmt(v) + unit)); hit.addEventListener('mouseleave', () => tip.hidden = true); svg.appendChild(hit);
  });
  return svg;
}
function cols(rows) {
  const W = 420, H = 210, m = { l: 34, r: 4, t: 10, b: 24 }, svg = el('svg', { width: '100%', viewBox: `0 0 ${W} ${H}`, height: H });
  const mx = Math.max(...rows.map(r => r[1]), 1), bw = (W - m.l - m.r) / rows.length, y = v => H - m.b - (H - m.b - m.t) * v / mx;
  [0, .25, .5, .75, 1].forEach(f => { const v = Math.round(mx * f); svg.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: 'var(--line)' })); svg.appendChild(el('text', { class: 't', x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, nf.format(v))); });
  rows.forEach(([l, v], i) => {
    const x = m.l + i * bw;
    svg.appendChild(el('rect', { x: x + bw * .12, y: y(v), width: bw * .76, height: H - m.b - y(v), rx: 3, fill: 'var(--bar)' }));
    if ((rows.length - 1 - i) % 2 === 0) svg.appendChild(el('text', { class: 't', x: x + bw / 2, y: H - 7, 'text-anchor': 'middle' }, l));
    const hit = el('rect', { x, y: m.t, width: bw, height: H - m.t - m.b, fill: 'transparent' });
    hit.addEventListener('mousemove', e => showTip(e, l + ': ' + nf.format(v) + ' tools')); hit.addEventListener('mouseleave', () => tip.hidden = true); svg.appendChild(hit);
  });
  return svg;
}
function card(title, note, svg) {
  const d = document.createElement('div'); d.className = 'card';
  const h = document.createElement('h2'); h.textContent = title; const p = document.createElement('p'); p.className = 'note'; p.textContent = note;
  d.append(h, p, svg); $('charts').appendChild(d);
}
const years = {}; let ymax = 2014;
D.forEach(r => { const y = parseInt(r.latest_release_year, 10); if (y >= 2014 && y <= 2100) { years[y] = (years[y] || 0) + 1; ymax = Math.max(ymax, y); } });
const yrows = []; for (let y = 2014; y <= ymax; y++) yrows.push([String(y), years[y] || 0]);
const fields = [['category', 'Category'], ['license_model', 'Licence model'], ['repository_url', 'Repository link'], ['website_url', 'Website link'], ['region', 'Region'], ['supported_platforms', 'Platforms'], ['languages_formats', 'Languages and formats'], ['latest_release_year', 'Latest release year'], ['first_release_year', 'First release year']];
const comp = fields.map(([f, l]) => [l, D.filter(r => !blank(r[f])).length / n]);
card('Tools by design-flow category', 'A tool counts once, under its main category.', bars(count('category', 'Not stated'), nf.format, 0, ' tools'));
card('Tools by region', 'From the vendor or maintainer country; not stated where none was found.', bars(count('region', 'Not stated'), nf.format, 0, ' tools'));
card('Top countries', 'Only tools whose country is known.', bars(count('country_region', '', 12), nf.format, 0, ' tools'));
card('Licence model', 'Open source, commercial or freeware, as stated by a source.', bars(count('license_model', 'Not stated'), nf.format, 0, ' tools'));
card('Top vendors and maintainers', 'Spellings of the same name are merged. Most open-source tools are listed under their GitHub owner.', bars(count('vendor_canonical', '', 12), nf.format, 0, ' tools'));
card('Latest release year', 'Only tools with a stated release, from 2014 on.', cols(yrows));
card('How complete the data is', 'Share of tools with each field filled. A gap means no source stated it.', bars(comp, pf, 1, ' of tools'));
// table
const C = [['tool_name', 'Tool'], ['vendor_canonical', 'Vendor or maintainer'], ['category', 'Category'], ['license_model', 'Licence'], ['region', 'Region'], ['country_region', 'Country'], ['latest_release_year', 'Latest release', 1], ['source_count', 'Sources', 1]];
const st = { q: '', fc: '', fl: '', fr: '', k: 'tool_name', d: 1, num: false };
function fill(sel, all, key) { sel.appendChild(new Option(all, '')); Array.from(new Set(D.map(r => r[key]).filter(v => !blank(v)))).sort().forEach(v => sel.appendChild(new Option(v, v))); }
fill($('fc'), 'All categories', 'category'); fill($('fl'), 'All licences', 'license_model'); fill($('fr'), 'All regions', 'region');
C.forEach(([k, l, num]) => { const th = document.createElement('th'), b = document.createElement('button'); b.type = 'button'; b.textContent = l; b.onclick = () => { if (st.k === k) st.d = -st.d; else { st.k = k; st.d = 1; } st.num = !!num; draw(); }; th.appendChild(b); $('head').appendChild(th); });
function draw() {
  const q = st.q.trim().toLowerCase();
  let rows = D.filter(r => (!q || (r.tool_name + ' ' + r.vendor_canonical).toLowerCase().includes(q)) && (!st.fc || r.category === st.fc) && (!st.fl || r.license_model === st.fl) && (!st.fr || r.region === st.fr));
  rows.sort((a, b) => {
    if (st.num) { const x = parseFloat(a[st.k]), y = parseFloat(b[st.k]), xn = isNaN(x), yn = isNaN(y); return xn || yn ? (xn === yn ? 0 : xn ? 1 : -1) : (x - y) * st.d; }
    const x = (a[st.k] || '').toLowerCase(), y = (b[st.k] || '').toLowerCase(); if (!x || !y) return x === y ? 0 : !x ? 1 : -1; return x < y ? -st.d : x > y ? st.d : 0;
  });
  const f = document.createDocumentFragment();
  rows.forEach(r => { const tr = document.createElement('tr'); C.forEach(([k]) => { const td = document.createElement('td'); if (k === 'tool_name' && /^https:\/\//.test(r.source_url)) { const a = document.createElement('a'); a.href = r.source_url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = r[k]; td.appendChild(a); } else td.textContent = r[k] || ''; tr.appendChild(td); }); f.appendChild(tr); });
  $('body').replaceChildren(f); $('none').hidden = rows.length > 0;
}
$('q').oninput = e => { st.q = e.target.value; draw(); };
[['fc', 'fc'], ['fl', 'fl'], ['fr', 'fr']].forEach(([id, k]) => $(id).onchange = e => { st[k] = e.target.value; draw(); });
draw();
</script></body></html>
"""


def main():
    if not SRC.exists():
        raise SystemExit("missing %s - run clean_data/deduplicate_data first" % SRC)
    with open(SRC, newline="", encoding="utf-8") as f:
        rows = [{k: (r.get(k) or "") for k in KEEP} for r in csv.DictReader(f)]
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    from datetime import datetime
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = PAGE.replace("__DATA__", data).replace("__BUILT__", built)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print("dashboard: %d tools -> %s" % (len(rows), OUT))


if __name__ == "__main__":
    main()
