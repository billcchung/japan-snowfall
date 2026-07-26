#!/usr/bin/env python3
"""
Pull historical snowfall for Japanese ski resorts from the Japan
Meteorological Agency and write one CSV of Nov-Apr ski seasons per resort.

Stdlib only. Run from anywhere with access to data.jma.go.jp.

    python3 jma_snowfall.py discover      # build station_index.json
    python3 jma_snowfall.py fetch         # season totals for every resort
    python3 jma_snowfall.py fetch niseko hakuba
    python3 jma_snowfall.py verify        # Kutchan vs the transcribed table
    python3 jma_snowfall.py daily         # daily snow and depth, incremental
    python3 jma_snowfall.py build         # regenerate index.html and plan.html

Resorts live in resorts.json, not in this file. This module handles the ones
whose source is "jma"; another country means another fetcher writing the same
CSV and data/daily/ shapes.

Notes on the source data
------------------------
JMA aggregates snow by 寒候年 (cold-season year): Aug 1 of the previous
calendar year to Jul 31 of the labelled year. The monthly table columns are
calendar months, so a ski season is assembled from two rows: Nov/Dec of
year N and Jan-Apr of year N+1.

The element pulled is 降雪の深さ月合計 -- the sum of daily new-snow depth in
cm, which is what "snowfall" means on resort marketing pages. It is not the
same as 最深積雪 (deepest snowpack).

Stations sit in the valley town, not on the mountain. On-hill totals run
higher, and by different amounts at different resorts, so treat
cross-resort comparison as indicative rather than exact.
"""

import csv
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://www.data.jma.go.jp/stats/etrn"
UA = "Mozilla/5.0 (compatible; personal snowfall research; stdlib urllib)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DAILY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "daily")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "station_index.json")
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "niseko_kutchan.csv")

# JMA region codes (prec_no). Hokkaido is split by subprefecture.
PREC = {
    11: "宗谷", 12: "上川", 13: "留萌", 14: "石狩", 15: "空知", 16: "後志",
    17: "網走・北見・紋別", 18: "根室", 19: "釧路", 20: "十勝", 21: "胆振",
    22: "日高", 23: "渡島", 24: "檜山",
    31: "青森県", 32: "秋田県", 33: "岩手県", 34: "宮城県", 35: "山形県",
    36: "福島県", 40: "茨城県", 41: "栃木県", 42: "群馬県", 43: "埼玉県",
    44: "東京都", 45: "千葉県", 46: "神奈川県", 48: "長野県", 49: "山梨県",
    50: "静岡県", 51: "愛知県", 52: "岐阜県", 53: "三重県", 54: "新潟県",
    55: "富山県", 56: "石川県", 57: "福井県", 60: "滋賀県", 61: "京都府",
    62: "大阪府", 63: "兵庫県", 64: "奈良県", 65: "和歌山県", 66: "岡山県",
    67: "広島県", 68: "島根県", 69: "鳥取県",
}

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "resorts.json")


def load_registry():
    """Every resort the site knows about, across all countries and sources.

    This file, not the table below, is the source of truth. Adding a country
    means adding entries with a different `source` plus a fetcher that writes
    the same CSV shape -- no change to this module.
    """
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


REGISTRY = load_registry()

# The subset this module can fetch, in the shape the JMA code already uses:
# resort -> (station name, region code, elevation-gap note).
RESORTS = {k: (v["station"]["name_ja"], v["station"]["prec_no"], v["note"])
           for k, v in REGISTRY.items() if v["source"] == "jma"}

MONTH_COLS = ["jan", "feb", "mar", "apr", "may", "jun", "jul",
              "aug", "sep", "oct", "nov", "dec"]

def grouping():
    """Country -> areas -> resort keys, in registry order.

    Drives the picker on both pages. Registry order is display order, so
    reordering resorts.json reorders the site.
    """
    tree = {}
    for k, v in REGISTRY.items():
        tree.setdefault(v["country"], {}).setdefault(v["area"], []).append(k)
    return tree


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

def get(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw.decode("utf-8", "replace")
        except Exception as e:
            if attempt == tries - 1:
                raise
            sys.stderr.write(f"  retry {attempt + 1}: {e}\n")
            time.sleep(3 * (attempt + 1))


# --------------------------------------------------------------------------
# station discovery
# --------------------------------------------------------------------------

# JMA's region maps call viewPoint('s'|'a', block_no, name_ja, name_kana, ...)
VIEWPOINT = re.compile(r"viewPoint\((.*?)\)", re.S)


def _args(blob):
    return [a.strip().strip("'\"") for a in blob.split(",")]


def _shape(args):
    """Locate elevation, and the snow flag that follows it.

    viewPoint(kind, block, name, kana, lat_d, lat_m, lon_d, lon_m, elev,
              f_pre, f_wsp, f_tem, f_sun, f_snc, f_hum, ...) -- so once the
    elevation is located, f_snc is five positions further on. Plenty of
    stations report wind and temperature but no snow at all; knowing that up
    front turns a mystifying empty-table failure into a checkable fact.
    """
    nums = []
    for a in args[4:]:
        try:
            nums.append(float(a))
        except ValueError:
            nums.append(None)
    for i in range(len(nums) - 4):
        lat_d, lat_m, lon_d, lon_m, elev = nums[i:i + 5]
        if None in (lat_d, lat_m, lon_d, lon_m, elev):
            continue
        if 24 <= lat_d <= 46 and 122 <= lon_d <= 154 and -5 <= elev <= 3800:
            # f_snc sits five positions past the elevation, whichever offset
            # the elevation was found at.
            #
            # Trust it for AMeDAS, where it is discriminating and catches a
            # station that reports wind and temperature but no snow. It says
            # nothing useful about surface stations: JMA flags all 112 of them
            # as snow-capable, 南鳥島 in the subtropical Pacific included. Read
            # it rather than assert it, but do not expect it to catch a bad
            # surface-station pick -- only an empty table will.
            at = 4 + i + 4 + 5
            snow = args[at] == "1" if at < len(args) else None
            return elev, snow
    return None, None


def discover():
    index = {}
    for prec, label in PREC.items():
        url = f"{BASE}/select/prefecture.php?prec_no={prec}&block_no=&year=&month=&day=&view="
        try:
            html = get(url)
        except Exception as e:
            sys.stderr.write(f"{prec} {label}: {e}\n")
            continue
        found = 0
        for blob in VIEWPOINT.findall(html):
            a = _args(blob)
            if len(a) < 4 or a[0] not in ("s", "a") or not a[1].isdigit():
                continue
            elev, snow = _shape(a)
            index[f"{prec}:{a[2]}"] = {
                "prec_no": prec, "region": label, "block_no": a[1],
                "kind": a[0], "name_ja": a[2], "kana": a[3],
                "elevation_m": elev, "snow": snow,
            }
            found += 1
        if not found:
            # fallback: pull block numbers straight out of any links on the map
            for block in set(re.findall(r"block_no=(\d{4,5})", html)):
                index[f"{prec}:block{block}"] = {
                    "prec_no": prec, "region": label, "block_no": block,
                    "kind": "s" if len(block) == 5 else "a",
                    "name_ja": "", "kana": "", "elevation_m": None, "snow": None,
                }
                found += 1
            if found:
                sys.stderr.write(
                    f"  prec {prec}: viewPoint markup not found, fell back to "
                    f"{found} block numbers without names\n")
        print(f"prec {prec:>2} {label:<12} {found:>3} stations")
        time.sleep(1.0)
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"\n{len(index)} stations -> {INDEX}")
    return index


def load_index():
    if not os.path.exists(INDEX):
        sys.exit("run 'discover' first")
    with open(INDEX, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# monthly snowfall table
# --------------------------------------------------------------------------

TAG = re.compile(r"<[^>]+>")
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_OPEN = re.compile(r"<t[dh][^>]*>", re.S | re.I)
CELL_CLOSE = re.compile(r"</t[dh]>", re.S | re.I)


def cell_text(html):
    return TAG.sub("", html).replace("&nbsp;", " ").strip()


def cells(row_html):
    """Split a row on opening cell tags, not matched pairs.

    JMA omits the closing </td> on the year cell of the surface monthly
    table, so matching <td>...</td> swallows the following cell and merges
    the two values -- 1953 and its January total arrive as "1953262". Every
    row then fails the column count and the table parses to nothing.
    """
    out = []
    for part in CELL_OPEN.split(row_html)[1:]:
        out.append(cell_text(CELL_CLOSE.split(part, 1)[0]))
    return out


def parse_number(s):
    """JMA marks values: ']' unreliable, ')' incomplete, '--' none, '#'/'×' missing."""
    s = s.replace("]", "").replace(")", "").replace("#", "").strip()
    if s in ("", "--", "×", "///", "/"):
        return 0 if s == "--" else None
    try:
        return float(s)
    except ValueError:
        return None


# The two station kinds need different endpoints.
#
# Surface stations ("s") publish monthly_s3.php, which returns every year of
# record in one table; snowfall is view=p6. Verified against Kutchan (47433).
#
# AMeDAS stations ("a") have no equivalent. Their station index offers only
# annually_a.php and the nml_amd_* normals, and monthly_a3.php -- which an
# earlier version of this script guessed at -- is a 404 everywhere. Monthly
# values come from monthly_a1.php, one calendar year per request.
SURFACE_URL = (BASE + "/view/monthly_s3.php?prec_no={prec}&block_no={block}"
               "&year=&month=&day=&view=p6")
AMEDAS_URL = (BASE + "/view/monthly_a1.php?prec_no={prec}&block_no={block}"
              "&year={year}&month=&day=&view=")
STATION_URL = (BASE + "/index.php?prec_no={prec}&block_no={block}"
               "&year=&month=&day=&view=")

YEAR_LINK = re.compile(r"index\.php\?prec_no=\d+&block_no=\w+&year=(\d{4})")


def monthly_surface(prec_no, block_no):
    url = SURFACE_URL.format(prec=prec_no, block=block_no)
    html = get(url)
    if "降雪の深さの月合計値" not in html:
        raise RuntimeError(f"no snowfall table at {url}")
    data = {}
    for row_html in ROW.findall(html):
        vals = cells(row_html)
        if len(vals) < 13:
            continue
        m = re.match(r"^(\d{4})$", vals[0])
        if not m:
            continue
        data[int(m.group(1))] = [parse_number(c) for c in vals[1:13]]
    if not data:
        raise RuntimeError(f"snowfall table at {url} parsed to nothing")
    return data, url


def amedas_years(prec_no, block_no):
    """The station index lists one link per year of record."""
    html = get(STATION_URL.format(prec=prec_no, block=block_no))
    years = sorted({int(y) for y in YEAR_LINK.findall(html)})
    if not years:
        raise RuntimeError(f"no year links for prec={prec_no} block={block_no}")
    return years


def monthly_amedas(prec_no, block_no):
    """One request per calendar year, twelve month rows each.

    Table width varies between stations -- those that skip wind, temperature
    or sunshine emit fewer columns -- so snowfall is read from the end. The
    three 雪 columns are always last and always ordered 降雪の深さ合計,
    降雪の深さ日合計の最大, 最深積雪.
    """
    years = amedas_years(prec_no, block_no)
    data = {}
    for year in years:
        url = AMEDAS_URL.format(prec=prec_no, block=block_no, year=year)
        try:
            html = get(url, tries=2)
        except Exception as e:
            sys.stderr.write(f"    {year}: {e}\n")
            continue
        if "降雪の深さ" not in html:
            continue
        months = [None] * 12
        for row_html in ROW.findall(html):
            vals = cells(row_html)
            if len(vals) < 4:
                continue
            m = re.match(r"^(\d{1,2})$", vals[0])
            if not m or not 1 <= int(m.group(1)) <= 12:
                continue
            months[int(m.group(1)) - 1] = parse_number(vals[-3])
        if any(v is not None for v in months):
            data[year] = months
        time.sleep(0.7)
    if not data:
        raise RuntimeError(
            f"no snowfall rows for prec={prec_no} block={block_no}; "
            f"station may not measure snow")
    return data, AMEDAS_URL.format(prec=prec_no, block=block_no, year=years[-1])


def monthly_table(prec_no, block_no, kind):
    """Return {year: [12 monthly snowfall values]}, calendar months."""
    if kind == "s":
        return monthly_surface(prec_no, block_no)
    return monthly_amedas(prec_no, block_no)


# --------------------------------------------------------------------------
# daily snowfall and snow depth
# --------------------------------------------------------------------------

# Monthly buckets cannot answer "how much falls between 25 Dec and 5 Jan",
# so trip planning needs day resolution. Same surface/AMeDAS split as above.
#
# Unlike the monthly tables, daily tables are a fixed width per station kind:
# elements a station does not measure come back as /// rather than being
# omitted, so 赤井川 (which measures little but snow) has the same 18 columns
# as 蘭越. Surface rows are 21 -- the extra three being two 天気概況 summary
# cells at the very end plus a pressure pair at the front. Counting the snow
# columns from the end is therefore safe for both.
DAILY_URL = {
    "s": BASE + "/view/daily_s1.php?prec_no={prec}&block_no={block}"
                "&year={year}&month={month}&day=&view=",
    "a": BASE + "/view/daily_a1.php?prec_no={prec}&block_no={block}"
                "&year={year}&month={month}&day=&view=",
}
SNOW_COL = {"s": -4, "a": -2}     # 降雪の深さ 日合計 (cm)
DEPTH_COL = {"s": -3, "a": -1}    # 最深積雪 (cm)

SEASON_MONTHS = [(0, 11), (0, 12), (1, 1), (1, 2), (1, 3), (1, 4)]


def daily_month(prec_no, block_no, kind, year, month):
    """One calendar month of daily new snow and snow depth, in cm."""
    url = DAILY_URL[kind].format(prec=prec_no, block=block_no,
                                 year=year, month=month)
    html = get(url, tries=2)
    snow, depth = [], []
    for row_html in ROW.findall(html):
        vals = cells(row_html)
        if len(vals) < 6 or not re.match(r"^\d{1,2}$", vals[0]):
            continue
        snow.append(parse_number(vals[SNOW_COL[kind]]))
        depth.append(parse_number(vals[DEPTH_COL[kind]]))
    if not snow:
        raise RuntimeError(f"no daily rows at {url}")
    return snow, depth


def season_years(resort):
    """The starting calendar year of every season in the resort's CSV."""
    path = os.path.join(OUT, f"{resort}.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [int(r["season"].split("/")[0]) for r in csv.DictReader(f)]


def daily(names):
    """Fill data/daily/<prec>-<block>.json, one entry per station-month.

    Cached months are skipped, so the first run is long and later runs only
    pick up the current season. Keyed by station rather than resort: 旭川
    serves both Asahidake and Kamui and is fetched once.
    """
    index = load_index()
    os.makedirs(DAILY, exist_ok=True)
    groups = {}
    for resort in names:
        station_ja, prec, _ = RESORTS[resort]
        groups.setdefault((prec, station_ja), []).append(resort)

    for (prec, station_ja), resorts in groups.items():
        st = index.get(f"{prec}:{station_ja}")
        if not st:
            sys.stderr.write(f"{'/'.join(resorts)}: {station_ja} not in index\n")
            continue
        years = season_years(resorts[0])
        if not years:
            sys.stderr.write(f"{'/'.join(resorts)}: no monthly CSV yet\n")
            continue
        path = os.path.join(DAILY, f"{st['prec_no']}-{st['block_no']}.json")
        cache = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
        latest = max(years)
        todo = []
        for y in years:
            for offset, month in SEASON_MONTHS:
                yy = y + offset
                key = f"{yy}-{month:02d}"
                # Refetch the newest season each run; JMA revises recent months.
                if key not in cache or y >= latest:
                    todo.append((yy, month, key))
        if not todo:
            print(f"{station_ja:<6} {len(cache):>4} months cached, nothing to do")
            continue
        done = 0
        for yy, month, key in todo:
            try:
                snow, depth = daily_month(st["prec_no"], st["block_no"],
                                          st["kind"], yy, month)
            except Exception as e:
                sys.stderr.write(f"  {station_ja} {key}: {e}\n")
                continue
            cache[key] = {"snow": snow, "depth": depth}
            done += 1
            time.sleep(1.0)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, separators=(",", ":"), sort_keys=True)
        print(f"{station_ja:<6} {'/'.join(resorts):<26} +{done:>4} months, "
              f"{len(cache):>4} cached -> {os.path.basename(path)}")


def to_seasons(monthly, resort, st, note):
    """Assemble Nov-Apr ski seasons from adjacent cold-season rows."""
    rows = []
    for y in sorted(monthly):
        if y + 1 not in monthly:
            continue
        nov, dec = monthly[y][10], monthly[y][11]
        jan, feb, mar, apr = monthly[y + 1][0:4]
        vals = [nov, dec, jan, feb, mar, apr]
        if all(v is None for v in vals):
            continue
        clean = [0 if v is None else v for v in vals]
        rows.append({
            "resort": resort,
            "station_ja": st["name_ja"],
            "prec_no": st["prec_no"],
            "block_no": st["block_no"],
            "season": f"{y}/{str(y + 1)[2:]}",
            "nov": clean[0], "dec": clean[1], "jan": clean[2],
            "feb": clean[3], "mar": clean[4], "apr": clean[5],
            "season_total_cm": round(sum(clean)),
            "incomplete": int(any(v is None for v in vals)),
            "note": note,
        })
    return rows


def fetch(names):
    index = load_index()
    os.makedirs(OUT, exist_ok=True)
    # Several resorts share a station -- Asahidake and Kamui are both 旭川,
    # Shiga Kogen borrows Nozawa's. Fetch each station once. That was a minor
    # saving when a station meant one request and matters now that an AMeDAS
    # station means one request per year of record.
    groups = {}
    for resort in names:
        station_ja, prec, _ = RESORTS[resort]
        groups.setdefault((prec, station_ja), []).append(resort)

    unresolved = []
    for (prec, station_ja), resorts in groups.items():
        who = "/".join(resorts)
        st = index.get(f"{prec}:{station_ja}")
        if not st:
            near = [k for k in index if k.startswith(f"{prec}:")][:8]
            sys.stderr.write(f"{who}: {station_ja} not in prec {prec}. "
                             f"Nearby keys: {near}\n")
            unresolved.append(f"{who}: {station_ja} not found in prec {prec}")
            continue
        # `is False` on purpose: None means discovery fell back to bare block
        # numbers and never learned the station's elements, which is not the
        # same as knowing it records nothing.
        if st.get("snow") is False:
            sys.stderr.write(f"{who}: {station_ja} does not measure snow\n")
            unresolved.append(f"{who}: {station_ja} (prec {prec}) records no snow")
            continue
        try:
            monthly, url = monthly_table(st["prec_no"], st["block_no"], st["kind"])
        except Exception as e:
            sys.stderr.write(f"{who}: {e}\n")
            continue
        for resort in resorts:
            note = RESORTS[resort][2]
            rows = to_seasons(monthly, resort, st, note)
            if not rows:
                sys.stderr.write(
                    f"{resort}: {station_ja} has a snowfall table but no "
                    f"adjacent-year pairs to build a season from\n")
                continue
            path = os.path.join(OUT, f"{resort}.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            span = f"{rows[0]['season']}-{rows[-1]['season']}"
            avg = round(sum(r["season_total_cm"] for r in rows[-25:])
                        / min(25, len(rows)))
            print(f"{resort:<16} {station_ja:<6} {len(rows):>3} seasons {span}  "
                  f"last-25 avg {avg:>5}cm")
        time.sleep(1.5)

    # A station that is missing from the index, or that records no snow, is a
    # mistake in resorts.json rather than a transient failure -- and it
    # silently drops the resort from every page. Fail loudly rather than
    # letting a green workflow hide it.
    if unresolved:
        sys.exit("\nunresolved stations (fix resorts.json):\n  "
                 + "\n  ".join(unresolved))


# --------------------------------------------------------------------------
# html
# --------------------------------------------------------------------------

def build():
    ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference.json")
    ref = {}
    if os.path.exists(ref_path):
        with open(ref_path, encoding="utf-8") as f:
            ref = json.load(f)
    index = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            index = json.load(f)
    payload = {}
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".csv"):
            continue
        with open(os.path.join(OUT, fn), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        key = rows[0]["resort"]
        st = index.get(f"{rows[0]['prec_no']}:{rows[0]['station_ja']}", {})
        meta = ref.get(key, {})
        meta_reg = REGISTRY.get(key, {})
        payload[key] = {
            "station_ja": rows[0]["station_ja"],
            "station_m": st.get("elevation_m"),
            "name": meta_reg.get("name", key),
            "country": meta_reg.get("country", ""),
            "area": meta_reg.get("area", ""),
            "region": st.get("region") or PREC.get(int(rows[0]["prec_no"]), ""),
            # Station-level daily file, fetched on demand by the planner.
            # Keyed by station so 旭川 is downloaded once for both resorts.
            "station_id": f"{rows[0]['prec_no']}-{rows[0]['block_no']}",
            "daily": (f"{rows[0]['prec_no']}-{rows[0]['block_no']}"
                      if os.path.exists(os.path.join(
                          DAILY, f"{rows[0]['prec_no']}-{rows[0]['block_no']}.json"))
                      else None),
            "areas": meta.get("areas", ""),
            "base": meta.get("base"),
            "top": meta.get("top"),
            "claimed_m": meta.get("claimed_m"),
            "note": rows[0].get("note", ""),
            "seasons": [{
                "s": r["season"],
                "m": [int(float(r[k])) for k in
                      ("nov", "dec", "jan", "feb", "mar", "apr")],
                "t": int(float(r["season_total_cm"])),
                "i": int(r.get("incomplete") or 0),
            } for r in rows],
        }
    # Resorts reading the same station produce identical series. Say so on the
    # page rather than leaving two matching lines looking like a bug -- 旭川
    # stands in for both Asahidake and Kamui, 1,500m below the former.
    # Group by the station itself, not by the daily file -- that file may not
    # have been fetched yet, and the resorts still share a series regardless.
    by_station = {}
    for key, v in payload.items():
        by_station.setdefault(v["station_id"], []).append(key)
    for group in by_station.values():
        if len(group) < 2:
            continue
        for key in group:
            payload[key]["shares"] = [payload[k]["name"] for k in group if k != key]

    here = os.path.dirname(os.path.abspath(__file__))
    # Only advertise countries and areas that actually have data, so an empty
    # heading never appears for resorts that have not been fetched yet.
    tree = {}
    for country, areas in grouping().items():
        for area, keys in areas.items():
            have = [k for k in keys if k in payload]
            if have:
                tree.setdefault(country, {})[area] = have
    blobs = {
        "/*__DATA__*/null": json.dumps(payload, ensure_ascii=False,
                                       separators=(",", ":")),
        "/*__GROUPS__*/null": json.dumps(tree, ensure_ascii=False,
                                         separators=(",", ":")),
        "/*__TOTAL__*/0": str(len(REGISTRY)),
    }
    for tpl_name, out_name in (("template.html", "index.html"),
                               ("plan-template.html", "plan.html"),
                               ("trends-template.html", "trends.html")):
        tpl = os.path.join(here, tpl_name)
        if not os.path.exists(tpl):
            continue
        with open(tpl, encoding="utf-8") as f:
            html = f.read()
        for token, blob in blobs.items():
            html = html.replace(token, blob)
        with open(os.path.join(here, out_name), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"{len(payload)} resorts -> {out_name}")


# --------------------------------------------------------------------------
# regression check
# --------------------------------------------------------------------------

def verify():
    """Check the scraped Kutchan series against the hand-transcribed table.

    Kutchan is the one station whose numbers were confirmed independently
    against Ski Asia's published figures, so it is the canary for a JMA
    markup change that parses without erroring but returns the wrong column.
    """
    scraped = os.path.join(OUT, "niseko.csv")
    if not os.path.exists(scraped):
        sys.exit("no data/niseko.csv -- run 'fetch niseko' first")
    if not os.path.exists(FIXTURE):
        sys.exit(f"missing fixture {FIXTURE}")
    with open(scraped, encoding="utf-8") as f:
        got = {r["season"]: int(float(r["season_total_cm"]))
               for r in csv.DictReader(f)}
    with open(FIXTURE, encoding="utf-8") as f:
        want = {r["season"]: int(float(r["season_total_cm"]))
                for r in csv.DictReader(f)}
    bad = []
    for season in sorted(want):
        if season not in got:
            bad.append(f"  {season}: missing from scrape")
        elif got[season] != want[season]:
            bad.append(f"  {season}: scraped {got[season]}cm, "
                       f"fixture {want[season]}cm")
    if bad:
        sys.stderr.write(f"FAIL {len(bad)} of {len(want)} seasons differ:\n")
        sys.stderr.write("\n".join(bad[:20]) + "\n")
        sys.exit(1)
    print(f"OK  {len(want)} Kutchan seasons match the transcribed table")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "discover":
        discover()
    elif cmd == "fetch":
        fetch(sys.argv[2:] or list(RESORTS))
    elif cmd == "daily":
        daily(sys.argv[2:] or list(RESORTS))
    elif cmd == "build":
        build()
    elif cmd == "verify":
        verify()
    else:
        sys.exit(__doc__)
