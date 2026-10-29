#!/usr/bin/env python3
"""
Check that the three languages agree.

    python3 i18n_check.py

Exits non-zero on any of:
  - a key in locales/en.js that another language lacks, or the reverse
  - {placeholders} that differ between languages for the same key
  - a plural key (`.one` / `.other`) with no `.other` in some language
  - a key used by a page or script that en.js does not define
  - English text left in a template's markup that differs from en.js, which is
    what a visitor sees with scripts off and what the English page shows first
  - a resort in resorts.json with no ja / zh-Hant name (a warning only: the
    page falls back to the English name)

Locale files are `I18N.add("<code>", { strict JSON });`, so they parse here
without a JavaScript engine.
"""

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = ["en", "ja", "zh-Hant"]
SOURCES = ["i18n.js", "site.js", "template.html", "plan-template.html",
           "trends-template.html", "map-template.html"]
PREFIXES = r"(?:idx|plan|trends|map|picker|ctl|shell|nav|lang|c|month|area|country)"

errors, warnings = [], []


def load(code):
    path = os.path.join(HERE, "locales", code + ".js")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.fullmatch(r'\s*I18N\.add\("([\w-]+)",\s*(\{.*\})\);\s*', text, re.S)
    if not m or m.group(1) != code:
        errors.append(f"{path}: not of the form I18N.add(\"{code}\", {{...}});")
        return {}
    try:
        return json.loads(m.group(2))
    except ValueError as e:
        errors.append(f"{path}: {e}")
        return {}


def holes(s):
    return sorted(set(re.findall(r"\{(\w+)\}", s)))


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def main():
    d = {code: load(code) for code in LANGS}
    en = d["en"]

    # A plural key is a stem with both `.one` and `.other` in English.
    plural = {k[:-4] for k in en if k.endswith(".one") and k[:-4] + ".other" in en}

    for code in LANGS[1:]:
        for k in sorted(set(en) - set(d[code])):
            if k.endswith(".one") and k[:-4] in plural:
                continue          # languages without a singular need only .other
            errors.append(f"{code}: missing key {k}")
        for k in sorted(set(d[code]) - set(en)):
            errors.append(f"{code}: key {k} is not in en")
        for k in sorted(set(en) & set(d[code])):
            if k == "date":       # each language orders and names the parts its own way
                if not set(holes(d[code][k])) <= {"d", "m", "n"}:
                    errors.append(f"{code}: date uses {holes(d[code][k])}, only d, m and n are given")
            elif holes(en[k]) != holes(d[code][k]):
                errors.append(f"{code}: {k} has {holes(d[code][k])}, en has {holes(en[k])}")
    for code in LANGS:
        for stem in plural:
            if stem + ".other" not in d[code]:
                errors.append(f"{code}: {stem} has no .other form")

    # Keys the code asks for. Any string literal shaped like a key counts, which
    # also catches the ternaries and "prefix." + name forms; a trailing dot is a
    # prefix that must match at least one key.
    used = set()
    for name in SOURCES:
        src = read(name)
        for m in re.finditer(r'["\':](' + PREFIXES + r'\.[\w.&, ]*?)["\']', src):
            used.add(m.group(1))
        for m in re.finditer(r'data-i18n(?:-attrs)?="([^"]*\.[^"]*)"', src):
            for part in m.group(1).split(","):
                used.add(part.split(":")[-1].strip())
        for m in re.finditer(r'\bT\(\s*"(\w[\w.]*)"', src):
            used.add(m.group(1))
    used = {u for u in used if not u.endswith(".html") and not u.startswith("nav.pages")}
    for k in sorted(used):
        if k.endswith("."):
            if not any(e.startswith(k) for e in en):
                errors.append(f"code asks for keys under {k}, none defined")
        elif k not in en and k not in plural:
            errors.append(f"code asks for {k}, not in en")
    known = {k[:-6] if k[:-6] in plural and k.endswith(".other")
             else k[:-4] if k[:-4] in plural and k.endswith(".one") else k for k in en}
    for k in sorted(known):
        if k.startswith("month.") or k.startswith("area.") or k.startswith("country."):
            continue
        if not any(u == k or (u.endswith(".") and k.startswith(u)) for u in used):
            warnings.append(f"{k} is defined but nothing asks for it")

    # English left in the markup must match en.js.
    for name in SOURCES[2:]:
        src = read(name)
        for m in re.finditer(r"<(\w+)\b([^>]*)>", src):
            tag, attrs = m.group(1), m.group(2)
            body = re.search(r'\bdata-i18n="([^"]+)"', attrs)
            if body:
                end = src.find("</" + tag + ">", m.end())
                inner = src[m.end():end]
                k = body.group(1)
                if k in en and norm(inner) != norm(en[k]):
                    errors.append(f"{name}: markup for {k} differs from en.js")
            for pair in re.findall(r'data-i18n-attrs="([^"]+)"', attrs):
                for part in pair.split(","):
                    attr, k = [x.strip() for x in part.split(":")]
                    val = re.search(r'\s' + re.escape(attr) + r'="([^"]*)"', attrs)
                    if val and k in en and norm(val.group(1)) != norm(en[k]):
                        errors.append(f"{name}: {attr} for {k} differs from en.js")

    with open(os.path.join(HERE, "resorts.json"), encoding="utf-8") as f:
        registry = json.load(f)
    with open(os.path.join(HERE, "reference.json"), encoding="utf-8") as f:
        ref = json.load(f)
    for key, v in registry.items():
        for code in LANGS[1:]:
            if not (v.get("names") or {}).get(code):
                warnings.append(f"resorts.json: {key} has no {code} name")
            if ref.get(key, {}).get("areas") and not (ref[key].get("areas_i18n") or {}).get(code):
                warnings.append(f"reference.json: {key} has no {code} areas")
    areas = {v["area"] for v in registry.values()} | {v["country"] for v in registry.values()}
    for a in sorted(areas):
        for pre in ("area.", "country."):
            if pre + a in en or pre + a in d["ja"]:
                break
        else:
            errors.append(f"resorts.json: no area.{a} / country.{a} in the locale files")

    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("error:", e)
    print(f"{len(en)} keys, {len(LANGS)} languages, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
