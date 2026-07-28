#!/usr/bin/env python3
"""
Turn the resort registry and whatever data has been fetched into the site.

    python3 site.py build

Deliberately knows nothing about any weather service. It reads resorts.json,
reference.json and data/*.csv, and writes index.html, plan.html and
trends.html. Each country's fetcher is responsible for producing CSVs in the
shape below; this step never opens a source-specific index or code table.

Required CSV columns per resort, one row per season:

    resort, source, station, station_id, station_m, region, season,
    oct..may, season_total_cm, incomplete, note

`station_m` may be blank. `station_id` need only be unique within a source --
the daily cache is filed as data/daily/<source>-<station_id>.json, so two
services may number their stations however they like.
"""

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")
DAILY = os.path.join(HERE, "data", "daily")
REGISTRY_PATH = os.path.join(HERE, "resorts.json")
REFERENCE_PATH = os.path.join(HERE, "reference.json")

# The ski season this site publishes: 1 Oct - 31 May. Emitted into each page so
# the front end derives its day axis from here rather than repeating the
# months as literals.
SEASON_COLS = ["oct", "nov", "dec", "jan", "feb", "mar", "apr", "may"]
SEASON_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5]
# Maximum length, so 29 Feb always has a slot; a non-leap season leaves it empty.
MONTH_DAYS = {10: 31, 11: 30, 12: 31, 1: 31, 2: 29, 3: 31, 4: 30, 5: 31}

PAGES = (("template.html", "index.html"),
         ("plan-template.html", "plan.html"),
         ("trends-template.html", "trends.html"))


def load_registry():
    """Every resort the site knows about, across all countries and sources."""
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def grouping(registry):
    """Country -> areas -> resort keys, in registry order.

    Registry order is display order, so reordering resorts.json reorders the
    picker on every page.
    """
    tree = {}
    for k, v in registry.items():
        tree.setdefault(v["country"], {}).setdefault(v["area"], []).append(k)
    return tree


def season_spec():
    return {"months": SEASON_MONTHS,
            "len": {str(m): MONTH_DAYS[m] for m in SEASON_MONTHS},
            "days": sum(MONTH_DAYS[m] for m in SEASON_MONTHS),
            # Months at or after this belong to the season's first calendar
            # year; the rest to the second. Northern hemisphere for now.
            "wrap": SEASON_MONTHS[0]}


def build():
    registry = load_registry()
    ref = {}
    if os.path.exists(REFERENCE_PATH):
        with open(REFERENCE_PATH, encoding="utf-8") as f:
            ref = json.load(f)

    payload = {}
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".csv"):
            continue
        with open(os.path.join(OUT, fn), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        key = rows[0]["resort"]
        if key not in registry:
            sys.stderr.write(f"{fn}: '{key}' is not in resorts.json, skipping\n")
            continue
        head, meta, reg = rows[0], ref.get(key, {}), registry[key]
        station_id = head.get("station_id", "")
        source = head.get("source", reg.get("source", ""))
        # Everything the page needs comes from the CSV and the registry, so a
        # second country's fetcher needs no change here.
        daily_id = f"{source}-{station_id}" if source and station_id else None
        if daily_id and not os.path.exists(os.path.join(DAILY, daily_id + ".json")):
            daily_id = None
        try:
            station_m = float(head.get("station_m") or "")
        except ValueError:
            station_m = None
        payload[key] = {
            "name": reg.get("name", key),
            "country": reg.get("country", ""),
            "area": reg.get("area", ""),
            "region": head.get("region", ""),
            "station": head.get("station", ""),
            "source": source,
            "station_id": station_id,
            "station_m": station_m,
            "daily": daily_id,
            "areas": meta.get("areas", ""),
            "base": meta.get("base"),
            "top": meta.get("top"),
            "claimed_m": meta.get("claimed_m"),
            "note": head.get("note", ""),
            "seasons": [{
                "s": r["season"],
                "m": [int(float(r[c] or 0)) for c in SEASON_COLS],
                "t": int(float(r["season_total_cm"])),
                "i": int(r.get("incomplete") or 0),
            } for r in rows],
        }

    # Resorts reading the same station produce identical series. Say so on the
    # page rather than leaving two matching lines looking like a bug.
    by_station = {}
    for key, v in payload.items():
        by_station.setdefault((v["country"], v["station_id"]), []).append(key)
    for group in by_station.values():
        if len(group) > 1:
            for key in group:
                payload[key]["shares"] = [payload[k]["name"] for k in group if k != key]

    # Only advertise countries and areas that actually have data.
    tree = {}
    for country, areas in grouping(registry).items():
        for area, keys in areas.items():
            have = [k for k in keys if k in payload]
            if have:
                tree.setdefault(country, {})[area] = have

    blobs = {
        "/*__DATA__*/null": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "/*__GROUPS__*/null": json.dumps(tree, ensure_ascii=False, separators=(",", ":")),
        "/*__SEASON__*/null": json.dumps(season_spec(), separators=(",", ":")),
        "/*__TOTAL__*/0": str(len(registry)),
    }
    for tpl_name, out_name in PAGES:
        tpl = os.path.join(HERE, tpl_name)
        if not os.path.exists(tpl):
            continue
        with open(tpl, encoding="utf-8") as f:
            html = f.read()
        for token, blob in blobs.items():
            html = html.replace(token, blob)
        with open(os.path.join(HERE, out_name), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"{len(payload)} resorts -> {out_name}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    else:
        sys.exit(__doc__)
