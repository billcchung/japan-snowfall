#!/usr/bin/env python3
"""
Pull historical snowfall for Japanese ski resorts from the Japan
Meteorological Agency and write one CSV of Nov-Apr ski seasons per resort.

Stdlib only. Run from anywhere with access to data.jma.go.jp.

    python3 jma_snowfall.py discover      # build station_index.json
    python3 jma_snowfall.py fetch         # pull every resort in RESORTS
    python3 jma_snowfall.py fetch niseko hakuba
    python3 jma_snowfall.py build         # regenerate index.html
    python3 jma_snowfall.py verify        # Kutchan vs the transcribed table

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

# resort -> the JMA station that best represents it.
# Second element is the region code, third is a note on the elevation gap.
RESORTS = {
    # --- Hokkaido ---
    "niseko":            ("倶知安", 16, "Valley town station below the Hirafu base"),
    "niseko-annupuri":   ("蘭越", 16, "Rankoshi 40m; west side of the same massif"),
    "rusutsu":           ("喜茂別", 16, "Kimobetsu 130m; Rusutsu base ~400m"),
    "kiroro":            ("赤井川", 16, "Akaigawa 220m; Kiroro base 570m, top 1180m"),
    "sapporo":           ("札幌", 14, "Sapporo 17m; Teine and Kokusai sit far above the city"),
    "furano":            ("富良野", 12, "Furano 173m; resort base 235m, top 1074m"),
    "tomamu":            ("占冠", 12, "Shimukappu 250m; Tomamu base 545m"),
    "asahidake":         ("旭川", 12, "Asahikawa 120m; Asahidake ropeway base 1100m — big gap"),
    "sahoro":            ("新得", 20, "Shintoku 177m; Sahoro base 480m"),
    "kamui":             ("旭川", 12, "Asahikawa 120m; Kamui Ski Links base 250m"),
    # --- Tohoku ---
    "hakkoda":           ("酸ケ湯", 31, "Sukayu 890m — on-mountain, Japan's deepest snowpack station"),
    "appi":              ("荒屋", 33, "Araya 320m; Appi base 500m"),
    "geto":              ("湯田", 33, "Yuda 235m; Geto Kogen base 430m"),
    "zao":               ("山形", 35, "Yamagata 153m; Zao base 780m — large gap, city undercounts"),
    "ani":               ("阿仁合", 32, "Aniai 90m; Ani base 200m"),
    "aomori-spring":     ("鰺ケ沢", 31, "Ajigasawa 40m; resort base 200m"),
    "nekoma-alts":       ("猪苗代", 36, "Inawashiro 514m; Nekoma and Alts sit above"),
    # --- Niigata / Nagano ---
    "myoko":             ("関山", 54, "Sekiyama 350m; Akakura base 450m"),
    "lotte-arai":        ("新井", 54, "Arai 40m; resort base 330m"),
    "nozawa":            ("野沢温泉", 48, "Nozawa Onsen 570m; village-level station, top 1650m"),
    "madarao":           ("飯山", 48, "Iiyama 313m; Madarao base 1000m"),
    "hakuba":            ("白馬", 48, "Hakuba 703m; Happo base 760m — unusually well matched"),
    "hakuba-north":      ("小谷", 48, "Otari 520m; Tsugaike and Cortina bases 800-900m"),
    "shiga-kogen":       ("野沢温泉", 48, "PROXY ONLY. No Shiga station; Shiga base is 1300-2300m"),
    "yuzawa":            ("湯沢", 54, "Yuzawa 240m; Gala/Ishiuchi/Naeba/Kagura all draw from here"),
    "itoigawa":          ("糸魚川", 54, "Itoigawa 3m; Charmant Hiuchi base 400m"),
    # --- Gunma / Tochigi / Gifu ---
    "minakami":          ("藤原", 42, "Fujiwara 700m; Tanigawadake and Hodaira above"),
    "nasu":              ("那須高原", 41, "Nasu Kogen 749m"),
    "takasu":            ("長滝", 52, "Nagataki 470m; Takasu and Dynaland bases 900m+"),
}

MONTH_COLS = ["jan", "feb", "mar", "apr", "may", "jun", "jul",
              "aug", "sep", "oct", "nov", "dec"]

# Coarse grouping for the resort picker, in display order.
AREAS = ["Hokkaido", "Tohoku", "Niigata & Nagano", "Elsewhere"]


def area_for(prec_no):
    p = int(prec_no)
    if 11 <= p <= 24:
        return "Hokkaido"
    if 31 <= p <= 36:
        return "Tohoku"
    if p in (48, 54):
        return "Niigata & Nagano"
    return "Elsewhere"


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


def _elevation(args):
    """JMA passes lat_deg, lat_min, lon_deg, lon_min, elevation after the
    region code. Elevation is the first plausible altitude after the
    longitude minutes; return None rather than guess if the shape differs."""
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
            return elev
    return None


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
            index[f"{prec}:{a[2]}"] = {
                "prec_no": prec, "region": label, "block_no": a[1],
                "kind": a[0], "name_ja": a[2], "kana": a[3],
                "elevation_m": _elevation(a),
            }
            found += 1
        if not found:
            # fallback: pull block numbers straight out of any links on the map
            for block in set(re.findall(r"block_no=(\d{4,5})", html)):
                index[f"{prec}:block{block}"] = {
                    "prec_no": prec, "region": label, "block_no": block,
                    "kind": "s" if len(block) == 5 else "a",
                    "name_ja": "", "kana": "", "elevation_m": None,
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

    for (prec, station_ja), resorts in groups.items():
        who = "/".join(resorts)
        st = index.get(f"{prec}:{station_ja}")
        if not st:
            near = [k for k in index if k.startswith(f"{prec}:")][:8]
            sys.stderr.write(f"{who}: {station_ja} not in prec {prec}. "
                             f"Nearby keys: {near}\n")
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
        payload[key] = {
            "station_ja": rows[0]["station_ja"],
            "station_m": st.get("elevation_m"),
            "region": st.get("region") or PREC.get(int(rows[0]["prec_no"]), ""),
            "area": area_for(rows[0]["prec_no"]),
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
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
    with open(tpl, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/*__DATA__*/null",
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{len(payload)} resorts -> {out}")


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
    elif cmd == "build":
        build()
    elif cmd == "verify":
        verify()
    else:
        sys.exit(__doc__)
