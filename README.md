# Japan snowfall

Historical snowfall for Japanese ski resorts, taken from Japan Meteorological
Agency station records instead of resort marketing figures. A static site — no
build tooling, no dependencies, one Python script.

## Where it lives

<https://billcchung.github.io/japan-snowfall/>

Served by GitHub Pages from `main` at the repo root. Pushing to `main`
redeploys it; there is no build step.

## Coverage

All 40 resorts have season records — 21 in Hokkaido, 19 on Honshu. The trip
planner and trends pages additionally need the daily cache, which is filled
per station by `daily`. The weekly workflow keeps both current.

If the workflow can't push, check **Settings → Actions → General → Workflow
permissions** is set to *Read and write*.

To run it locally instead:

```bash
python3 jma_snowfall.py discover
python3 jma_snowfall.py fetch
python3 jma_snowfall.py verify
python3 jma_snowfall.py daily
python3 jma_snowfall.py build
```

Standard library only. `discover` is one request per prefecture. `fetch` is
one request per surface station but one request *per year of record* per
AMeDAS station. `daily` is one request per station-month, which is ~2,900 on a
cold start and ~54 afterwards because cached months are skipped. The script
rate limits itself throughout, because JMA asks people not to hammer the site.
Pass resort names to either command to do a subset.

## What's in the repo

| | |
|---|---|
| `resorts.json` | The resort registry — name, country, area, source, station. Source of truth. |
| `index.html` | Per-resort records. Generated — edit `template.html`. |
| `plan.html` | Multi-resort trip planner. Generated — edit `plan-template.html`. |
| `trends.html` | Season-by-season change per resort. Generated — edit `trends-template.html`. |
| `*-template.html` | Markup for the three pages. `/*__DATA__*/null`, `/*__GROUPS__*/null` and `/*__TOTAL__*/0` are where the data lands. |
| `site.css`, `site.js` | Shared styling and shared behaviour — picker, date controls, stats, daily cache. Each page defines its own `renderPage()`. |
| `jma_snowfall.py` | The Japan adapter: `discover`, `fetch`, `verify`, `daily`, `build`. Reads `resorts.json`. |
| `data/*.csv` | One file per resort, one row per season. Generated. |
| `data/daily/*.json` | Daily new snow and snow depth, one file per station. Generated, cached. |
| `reference.json` | Resort elevations and claimed annual snowfall. |
| `fixtures/niseko_kutchan.csv` | The hand-transcribed Kutchan table. `verify` checks the scrape against it. |
| `seed_kutchan.py` | Prints that fixture to stdout: `python3 seed_kutchan.py > fixtures/niseko_kutchan.csv`. |

## Reading the numbers

The element is 降雪の深さ月合計 — daily new-snow depth summed over the month. Not
snowpack depth (最深積雪), and not the cumulative figure resorts advertise.

JMA files snow by 寒候年, the cold-season year running 1 August to 31 July, so a
ski season spans two rows of the source table: November and December from one
calendar year, January through April from the next. Read the table naively and
every season total comes out wrong. The script handles it.

Stations sit in the valley town, not on the mountain. Kutchan's station is about
a kilometre below the Niseko summit; Hakuba's is near the Happo base; Zao's is
down in Yamagata city. Compare a resort against its own history confidently,
against other resorts loosely. The site shows each station's elevation gap so
you can judge for yourself.

The Niseko series is validated against Ski Asia's published figures — 751 cm for
2025/26, 685 cm for 2019/20, 2,019 cm for 1969/70, 849 cm for the last-ten
average. All exact.

## Known weak spots

**Shiga Kogen** borrows Nozawa Onsen's station, 750 m lower and across the ridge.
There is no station on the plateau. Treat it as a placeholder or drop it from
`resorts.json`.

**The two station kinds need different endpoints.** Surface stations publish
`monthly_s3.php?view=p6`, every year of record in one table. AMeDAS stations
have no equivalent — their station index offers only `annually_a.php` and the
`nml_amd_*` normals — so they go through `monthly_a1.php?year=YYYY`, one
request per calendar year. Column position is read from the end of the row,
because stations that skip wind, temperature or sunshine emit fewer columns;
the three 雪 columns are always last.

**Daily tables split the same way but behave better.** Surface stations use
`daily_s1.php?year=&month=`, AMeDAS uses `daily_a1.php`. Unlike the monthly
tables these are a fixed width per kind — 21 columns and 18 — because an
element a station does not measure comes back as `///` rather than being
dropped. Snow is counted from the end: surface rows carry two trailing 天気概況
cells, so new snow is at `-4` and depth at `-3`, against `-2` and `-1` for
AMeDAS. Daily sums reconcile exactly with the monthly totals; that is the
cheapest check that the right column is being read.

**JMA omits a closing `</td>`** on the year cell of the surface monthly table,
so a naive `<td>…</td>` match merges the year with the January value and every
row fails its column count. `cells()` splits on opening tags for that reason.
If a table ever parses to zero rows, check that first.

**Station discovery** parses JMA's `viewPoint(...)` calls on the region maps. If
that markup changes there's a fallback that scrapes bare block numbers, but it
loses the station names, so `fetch` will then report stations missing.

## Adding resorts, and other countries

Adding a Japanese resort means one entry in `resorts.json` giving the station's
exact Japanese name and its region code. Grep `station_index.json` after
`discover` to find it. Registry order is display order.

Adding a country means entries with a different `source`, plus a fetcher that
writes the same per-resort CSV — `resort, station_ja, prec_no, block_no,
season, nov…apr, season_total_cm, incomplete, note` — and, for the planner, a
daily cache under `data/daily/` keyed `"YYYY-MM"` with `snow` and `depth`
arrays. `jma_snowfall.py` only claims registry entries whose `source` is
`jma`, so a second fetcher can sit alongside it without touching this one.
`build` reads whatever is in `data/` and groups the picker by country and
area, so a new country appears on both pages with no front-end change.

Data attribution in [ATTRIBUTION.md](ATTRIBUTION.md).
