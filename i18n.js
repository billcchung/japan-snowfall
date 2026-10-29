/* Language handling, shared by every page. Loaded before the page's own
   scripts and the locale files (locales/*.js), each of which calls I18N.add().

   Static text carries data-i18n="key" (innerHTML) or data-i18n-attrs="attr:key,
   attr:key" (attributes), with the English left in the markup as the no-JS
   fallback. Text built in script goes through T(key, vars).

   English is the source: a key missing from the chosen language falls back to
   it, and a key missing from both shows as itself. i18n_check.py keeps the
   three files in step. Plurals follow Intl.PluralRules -- give a key `.one` and
   `.other` forms and pass {n}; languages without plural forms need only
   `.other`. */

const I18N = (() => {
  const LANGS = [["en", "English"], ["ja", "日本語"], ["zh-Hant", "繁體中文"]];
  const dict = {};
  const subs = [];
  const STORE = "japan-snowfall.lang";
  let lang = "en";
  let explicit = false;     // chosen by link or click, not guessed from the browser

  /* Any Chinese maps to Traditional: it is the only Chinese this site has, and
     closer to a Simplified reader's own than English is. */
  function normalise(code){
    const c = String(code || "").toLowerCase();
    if(c.startsWith("ja")) return "ja";
    if(c.startsWith("zh")) return "zh-Hant";
    if(c.startsWith("en")) return "en";
    return null;
  }

  const stored = () => { try { return localStorage.getItem(STORE); } catch(e){ return null; } };
  const store = v => { try { localStorage.setItem(STORE, v); } catch(e){} };

  function detect(){
    const fromUrl = normalise(new URLSearchParams(location.search).get("lang"));
    if(fromUrl){ explicit = true; return fromUrl; }
    const saved = normalise(stored());
    if(saved){ explicit = true; return saved; }
    for(const l of (navigator.languages || [navigator.language])){
      const n = normalise(l);
      if(n) return n;
    }
    return "en";
  }

  function lookup(d, key, vars){
    if(!d) return undefined;
    if(key in d) return d[key];
    if(vars && vars.n != null){
      const cat = new Intl.PluralRules(lang).select(vars.n);
      if((key + "." + cat) in d) return d[key + "." + cat];
      if((key + ".other") in d) return d[key + ".other"];
    }
    return undefined;
  }

  function t(key, vars){
    let s = lookup(dict[lang], key, vars);
    if(s === undefined) s = lookup(dict.en, key, vars);
    if(s === undefined) return key;
    return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : s;
  }

  const has = key => !!(dict[lang] && key in dict[lang]) || !!(dict.en && key in dict.en);

  /* "A and B", "A, B and C" -- or the target language's equivalent. */
  function list(items){
    try { return new Intl.ListFormat(lang, {style: "long", type: "conjunction"}).format(items); }
    catch(e){ return items.join(", "); }
  }

  const num = n => Number(n).toLocaleString(lang);

  function link(a){
    const u = new URL(a.getAttribute("href"), location.href);
    u.searchParams.set("lang", lang);
    a.setAttribute("href", u.pathname.split("/").pop() + u.search);
  }

  function apply(root){
    root = root || document;
    document.documentElement.lang = lang;
    root.querySelectorAll("[data-i18n]").forEach(e => { e.innerHTML = t(e.dataset.i18n); });
    root.querySelectorAll("[data-i18n-attrs]").forEach(e => {
      e.dataset.i18nAttrs.split(",").forEach(pair => {
        const [attr, key] = pair.split(":").map(x => x.trim());
        e.setAttribute(attr, t(key));
      });
    });
    // Carry an explicit choice across the page links, so it survives a browser
    // that will not keep localStorage.
    if(explicit) root.querySelectorAll("nav.pages a").forEach(link);
    root.querySelectorAll(".lang button").forEach(b =>
      b.setAttribute("aria-pressed", b.dataset.lang === lang));
  }

  /* The CJK sans only has to be fetched by someone reading Chinese. */
  function fonts(){
    if(lang !== "zh-Hant" || document.getElementById("font-tc")) return;
    const l = document.createElement("link");
    l.id = "font-tc"; l.rel = "stylesheet";
    l.href = "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&display=swap";
    document.head.appendChild(l);
  }

  function switcher(){
    const nav = document.querySelector("nav.pages");
    if(!nav || nav.querySelector(".lang")) return;
    const box = document.createElement("div");
    box.className = "lang";
    box.setAttribute("role", "group");
    box.setAttribute("data-i18n-attrs", "aria-label:lang.label");
    LANGS.forEach(([code, label]) => {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.lang = code; b.lang = code; b.textContent = label;
      b.onclick = () => set(code);
      box.appendChild(b);
    });
    nav.appendChild(box);
  }

  function set(code){
    if(!normalise(code) || code === lang) return;
    lang = code; explicit = true;
    store(code);
    const u = new URL(location.href);
    u.searchParams.set("lang", code);
    history.replaceState(null, "", u);
    fonts();
    apply();
    subs.forEach(fn => fn());
  }

  lang = detect();
  fonts();
  // Scripts sit at the end of the body, so the navigation is already parsed.
  switcher();

  return {
    /* The page's own text is filled in as soon as the language being shown has
       arrived, which is before any script after the locale files runs. */
    add: (code, strings) => {
      dict[code] = Object.assign(dict[code] || {}, strings);
      if(code === lang) apply();
    },
    t, has, list, num, apply, set,
    onChange: fn => subs.push(fn),
    get lang(){ return lang; },
  };
})();

const T = I18N.t;

/* ---------- names that live in the data, not the dictionaries ---------- */
/* A resort's name and its ski-area blurb ride in the build payload, so adding a
   resort to resorts.json needs no change here. Anything not translated there
   shows its English. */
const nameOf = k => {
  const d = DATA[k];
  return d ? ((d.names && d.names[I18N.lang]) || d.name) : k;
};
const areasOf = k => {
  const d = DATA[k];
  return d ? ((d.areas_i18n && d.areas_i18n[I18N.lang]) || d.areas || "") : "";
};
/* Region and country headings are few enough to live in the dictionaries. */
const areaLabel = a => I18N.has("area." + a) ? T("area." + a) : a;
const countryLabel = c => I18N.has("country." + c) ? T("country." + c) : c;
const mname = m => T("month." + m);
