/* Shared by every page: constants, stats, the resort picker, the date
   controls, the daily-data cache and the hover readout. Each page defines
   its own renderPage() and calls bootShell() once its DATA is in scope. */

const el = id => document.getElementById(id);
const nameOf = k => (DATA[k] && DATA[k].name) || k;
const mean = a => a.reduce((x,y)=>x+y,0)/a.length;
const median = a => { const s=[...a].sort((x,y)=>x-y), h=s.length>>1;
  return s.length%2 ? s[h] : (s[h-1]+s[h])/2; };
const pct = (arr,p) => { const s=[...arr].sort((x,y)=>x-y);
  const i=(s.length-1)*p, lo=Math.floor(i), hi=Math.ceil(i);
  return lo===hi ? s[lo] : s[lo]+(s[hi]-s[lo])*(i-lo); };

/* Days are an ordinal across Nov 1 - Apr 30, so a range crossing the New Year
   is a contiguous slice. Slot 120 is 29 Feb, empty in three seasons of four. */
const MON = [11,12,1,2,3,4];
const MLEN = {11:30, 12:31, 1:31, 2:29, 3:31, 4:30};
const MNAME = {11:"Nov", 12:"Dec", 1:"Jan", 2:"Feb", 3:"Mar", 4:"Apr"};
const ORD = (() => { const o={}; let n=0; MON.forEach(m => {o[m]=n; n+=MLEN[m];}); return o; })();
const NDAYS = 182;
const ord = (m,d) => ORD[m] + d - 1;
const fromOrd = o => { for(const m of MON) if(o < ORD[m]+MLEN[m]) return {m, d:o-ORD[m]+1};
  return {m:4, d:30}; };
const isLeap = y => (y%4===0 && y%100!==0) || y%400===0;
const dateLabel = (m,d) => d + " " + MNAME[m];
const seasonLabel = y => y + "/" + String(y+1).slice(2);
/* Hues spread evenly across however many resorts are picked, so no two ever
   share a colour. Lightness and saturation alternate between neighbours,
   which is what keeps a large selection readable once the wheel gets crowded
   -- at 20 resorts adjacent hues are only 18 degrees apart. Starting at 205
   keeps a single pick the familiar blue. */
const colourOf = (i, n) => {
  const hue = Math.round((i * 360 / Math.max(1, n) + 205) % 360);
  return `hsl(${hue} ${i % 2 ? 62 : 72}% ${i % 2 ? 52 : 68}%)`;
};

const stdev = a => { const m = mean(a);
  return a.length < 2 ? 0 : Math.sqrt(a.reduce((s,v)=>s+(v-m)*(v-m),0)/(a.length-1)); };

let picked = [];
let hidden = new Set();   // toggled from the chart key, not the resort picker
let sel = {m1:12, d1:25, m2:1, d2:5};
let since = 20;

const cache = {};        // station file id -> {seasonYear: {snow, depth}}

/* Keyed by station file, so resorts sharing a station download it once. */
async function ensureDaily(k){
  const id = DATA[k] && DATA[k].daily;
  if(!id) return null;
  if(cache[id] !== undefined) return cache[id];
  let raw;
  try{
    const res = await fetch("data/daily/" + id + ".json");
    if(!res.ok) throw new Error(res.status);
    raw = await res.json();
  }catch(e){ cache[id] = null; return null; }
  const out = {};
  for(const key in raw){
    const [y, mm] = key.split("-").map(Number);
    const sy = mm >= 11 ? y : y - 1;
    if(!out[sy]) out[sy] = {snow:new Array(NDAYS).fill(null),
                            depth:new Array(NDAYS).fill(null)};
    const base = ORD[mm];
    raw[key].snow.forEach((v,i) => { if(base+i < NDAYS) out[sy].snow[base+i] = v; });
    raw[key].depth.forEach((v,i) => { if(base+i < NDAYS) out[sy].depth[base+i] = v; });
  }
  cache[id] = out;
  return out;
}

function expectedDays(a,b,sy){
  let n = b - a + 1;
  const f29 = ORD[2] + 28;
  if(a <= f29 && f29 <= b && !isLeap(sy+1)) n--;
  return n;
}

function windowStats(seasons, sy, a, b){
  const s = seasons[sy];
  if(!s) return null;
  let sum=0, have=0, pow=0, dsum=0, dn=0;
  for(let i=a;i<=b;i++){
    const v = s.snow[i];
    if(v != null){ sum += v; have++; if(v >= 20) pow++; }
    const dv = s.depth[i];
    if(dv != null){ dsum += dv; dn++; }
  }
  if(have < expectedDays(a,b,sy) * 0.8) return null;
  return {total:sum, powder:pow, depth: dn ? dsum/dn : null};
}

function scanCurve(seasons, L, years){
  const out = [];
  for(let s=0; s+L-1 < NDAYS; s++){
    const vals = [];
    years.forEach(y => { const w = windowStats(seasons, y, s, s+L-1); if(w) vals.push(w.total); });
    if(vals.length >= Math.max(3, years.length*0.5))
      out.push({start:s, mean:mean(vals), p10:pct(vals,0.1), p90:pct(vals,0.9)});
  }
  return out;
}

function buildPicker(){
  const have = Object.keys(DATA||{});
  if(have.length < TOTAL){
    const g = el("gap");
    g.hidden = false;
    g.innerHTML = have.length + " of " + TOTAL + " resorts have data. Run the update " +
      "workflow to fill in the rest.";
  }
  const nav = el("picker");
  const multi = !!el("clear");          // records page picks one at a time
  const multiCountry = Object.keys(GROUPS).length > 1;
  let firstArea = true;
  for(const country in GROUPS){
    for(const area in GROUPS[country]){
      const ks = GROUPS[country][area].filter(k => have.includes(k));
      if(!ks.length) continue;
      const g = document.createElement("div");
      g.className = "pgroup";
      // Open the first area and any area holding a selection; collapse the
      // rest, so adding regions does not push the controls off the screen.
      const open = firstArea || ks.some(k => picked.includes(k));
      firstArea = false;
      const head = document.createElement("button");
      head.type = "button";
      head.className = "pghead";
      head.setAttribute("aria-expanded", open);
      head.innerHTML = `<span class="caret">\u25B6</span>`
        + `<span>${multiCountry ? country + " \u00b7 " : ""}${area}</span>`
        + `<span class="n">${ks.length}</span><span class="rule"></span>`;
      head.onclick = () =>
        head.setAttribute("aria-expanded", head.getAttribute("aria-expanded") !== "true");
      const body = document.createElement("div");
      body.className = "pgbody";
      ks.forEach(k => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = nameOf(k);
        btn.dataset.k = k;
        btn.setAttribute("aria-pressed","false");
        btn.onclick = () => toggle(k);
        body.appendChild(btn);
      });
      g.append(head);
      if(multi){
        const acts = document.createElement("span");
        acts.className = "pgacts";
        const all = document.createElement("button");
        all.type = "button"; all.textContent = "All";
        all.onclick = () => {
          ks.forEach(k => { if(!picked.includes(k)) picked.push(k); });
          head.setAttribute("aria-expanded", "true");   // show what was just picked
          renderPage();
        };
        const none = document.createElement("button");
        none.type = "button"; none.textContent = "None";
        none.onclick = () => {
          picked = picked.filter(k => !ks.includes(k));
          renderPage();
        };
        acts.append(all, none);
        g.append(acts);
      }
      g.append(body);
      nav.appendChild(g);
    }
  }
  if(!multi) return;
  el("clear").onclick = () => { picked = []; renderPage(); };
  const areaAll = el("area-all");
  if(areaAll) areaAll.onclick = () => {
    nav.querySelectorAll('.pghead[aria-expanded=true] ~ .pgbody button').forEach(b => {
      if(!picked.includes(b.dataset.k)) picked.push(b.dataset.k);
    });
    renderPage();
  };
}

function toggle(k){
  const at = picked.indexOf(k);
  if(at > -1) picked.splice(at,1); else picked.push(k);
  renderPage();
}

function paintPicker(){
  el("picker").querySelectorAll("button").forEach(b => {
    const i = picked.indexOf(b.dataset.k);
    b.setAttribute("aria-pressed", i > -1);
    const c = i > -1 ? colourOf(i, picked.length) : "";
    b.style.setProperty("--swatch", c);
    b.style.color = c;
  });
  el("count").textContent = picked.length
    ? picked.length + " selected" : "none selected";
}

function fillDays(selId, m, keep){
  const s = el(selId);
  s.innerHTML = "";
  for(let d=1; d<=MLEN[m]; d++){
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    s.appendChild(o);
  }
  s.value = Math.min(keep, MLEN[m]);
  return Number(s.value);
}

function buildDateControls(){
  [["m1","d1"],["m2","d2"]].forEach(([mi,di],which) => {
    const ms = el(mi);
    MON.forEach(m => {
      const o = document.createElement("option");
      o.value = m; o.textContent = MNAME[m];
      ms.appendChild(o);
    });
    ms.value = which ? sel.m2 : sel.m1;
    ms.onchange = () => {
      if(which){ sel.m2 = Number(ms.value); sel.d2 = fillDays("d2", sel.m2, sel.d2); }
      else     { sel.m1 = Number(ms.value); sel.d1 = fillDays("d1", sel.m1, sel.d1); }
      normalise(); renderPage();
    };
    el(di).onchange = () => {
      if(which) sel.d2 = Number(el("d2").value); else sel.d1 = Number(el("d1").value);
      normalise(); renderPage();
    };
  });
  fillDays("d1", sel.m1, sel.d1);
  fillDays("d2", sel.m2, sel.d2);
  const ss = el("since");
  [10,15,20,25,30,0].forEach(n => {
    const o = document.createElement("option");
    o.value = n; o.textContent = n ? "the last " + n + " seasons" : "every season on record";
    ss.appendChild(o);
  });
  ss.value = since;
  ss.onchange = () => { since = Number(ss.value); renderPage(); };
}

function normalise(){
  if(ord(sel.m2, sel.d2) < ord(sel.m1, sel.d1)){
    sel.m2 = sel.m1; sel.d2 = sel.d1;
    el("m2").value = sel.m2; fillDays("d2", sel.m2, sel.d2);
  }
  el("m1").value = sel.m1; el("d1").value = sel.d1;
  el("m2").value = sel.m2; el("d2").value = sel.d2;
}

function axes(W,H,P,maxv,Xof){
  const iw=W-P.l-P.r, ih=H-P.t-P.b;
  let g = "";
  [0,0.5,1].forEach(f => { const v=maxv*f, y=P.t+ih-(f*ih);
    g += `<line class="grid" x1="${P.l}" y1="${y.toFixed(1)}" x2="${P.l+iw}" y2="${y.toFixed(1)}"/>`
       + `<text class="axis" x="${P.l-6}" y="${(y+3).toFixed(1)}" text-anchor="end">${Math.round(v)}</text>`; });
  MON.forEach(m => { const x=Xof(ORD[m]);
    g += `<line class="grid" x1="${x.toFixed(1)}" y1="${P.t}" x2="${x.toFixed(1)}" y2="${P.t+ih}"/>`
       + `<text class="axis" x="${(x+3).toFixed(1)}" y="${H-9}">${MNAME[m]}</text>`; });
  return g;
}

function attachHover(host, model){
  const svg = host.querySelector("svg");
  if(!svg || !model) return;
  let tip = host.querySelector(".tip");
  if(!tip){ tip = document.createElement("div"); tip.className = "tip"; host.appendChild(tip); }
  const guide = svg.querySelector(".guide");
  const dots = [...svg.querySelectorAll(".hit")];
  const hide = () => {
    tip.style.opacity = "0";
    if(guide) guide.setAttribute("opacity","0");
    dots.forEach(d => d.setAttribute("opacity","0"));
  };
  hide();
  const move = pt => {
    const r = svg.getBoundingClientRect();
    if(!r.width) return;
    const hit = model.at((pt.clientX - r.left) / r.width * model.W);
    if(!hit) return hide();
    if(guide){ guide.setAttribute("opacity","1");
      guide.setAttribute("x1", hit.x.toFixed(1)); guide.setAttribute("x2", hit.x.toFixed(1)); }
    dots.forEach((d,i) => {
      const row = hit.rows[i];
      if(!row){ d.setAttribute("opacity","0"); return; }
      d.setAttribute("opacity","1");
      d.setAttribute("cx", hit.x.toFixed(1)); d.setAttribute("cy", row.y.toFixed(1));
    });
    tip.innerHTML = `<b>${hit.label}</b>` + hit.rows.map(row =>
      `<span><i style="background:${row.colour}"></i>${row.name}<em>${row.value}`
      + (row.extra ? `<u>${row.extra}</u>` : "") + `</em></span>`).join("");
    tip.style.opacity = "1";
    const px = hit.x / model.W * r.width;
    const w = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(px + 14, r.width - w - 4)) + "px";
  };
  svg.addEventListener("mousemove", e => move(e));
  svg.addEventListener("mouseleave", hide);
  svg.addEventListener("touchstart", e => { if(e.touches[0]) move(e.touches[0]); }, {passive:true});
  svg.addEventListener("touchmove", e => { if(e.touches[0]) move(e.touches[0]); }, {passive:true});
}



/* One comparable series per picked resort for the chosen window. Pages differ
   in what they draw from it, not in how it is derived. */
async function seriesFor(a, b, L){
  const loaded = await Promise.all(picked.map(ensureDaily));
  const out = [];
  picked.forEach((k, i) => {
    const seasons = loaded[i];
    if(!seasons) return;
    const all = Object.keys(seasons).map(Number).sort((x,y)=>x-y);
    const years = since ? all.slice(-since) : all;
    const rows = [];
    years.forEach(y => { const w = windowStats(seasons, y, a, b); if(w) rows.push({y, ...w}); });
    if(rows.length < 3) return;
    const totals = rows.map(r => r.total);
    const depths = rows.filter(r => r.depth != null).map(r => r.depth);
    const avg = mean(totals), sd = stdev(totals);
    out.push({
      k, name:nameOf(k), area:DATA[k].area, colour:colourOf(i, picked.length),
      seasons, rows, totals, curve:scanCurve(seasons, L, years),
      avg, med:median(totals), sd, cv: avg ? sd / avg * 100 : 0,
      p10:pct(totals,0.1), p25:pct(totals,0.25),
      p75:pct(totals,0.75), p90:pct(totals,0.9),
      powder:mean(rows.map(r => r.powder)),
      base: depths.length ? mean(depths) : null,
    });
  });
  return out;
}

function bootShell(defaultPicks){
  const have = Object.keys(DATA || {});
  if(!have.length){
    document.body.innerHTML = "<div class='wrap'><header><h1>No data yet</h1>"
      + "<p class='lede'>Run <code>jma_snowfall.py fetch</code>, then <code>daily</code>, "
      + "then <code>build</code>.</p></header></div>";
    return;
  }
  buildDateControls();
  // Open on distinct stations in registry order -- two identical series reads
  // as a bug rather than a fact.
  const seen = new Set();
  outer:
  for(const country in GROUPS)
    for(const area in GROUPS[country])
      for(const k of GROUPS[country][area]){
        if(!have.includes(k)) continue;
        const id = DATA[k].daily;
        if(id && seen.has(id)) continue;
        if(id) seen.add(id);
        picked.push(k);
        if(picked.length === (defaultPicks || 3)) break outer;
      }
  buildPicker();
  renderPage();
}
