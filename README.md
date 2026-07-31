# Japan snowfall

Historical snowfall for Japanese ski resorts, taken from Japan Meteorological
Agency station records instead of resort marketing figures. A static site — no
build tooling, no dependencies, standard library only.

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
python3 jma_snowfall.py survey
python3 site.py build
```

Standard library only, and rate limited throughout because JMA asks people not
to hammer the site. `discover` is one request per prefecture, about 50.
`fetch` is one request per surface station but one *per year of record* per
AMeDAS station, roughly 1,400 in all. `daily` is one request per station-month:
about 14,000 from cold, and ~300 on a weekly run because cached months are
skipped. `survey` is one request per snow-recording station, about 350, and is
independent of the resort list — it uses JMA's annual (寒候年) tables, where a
station's whole record arrives in a single request. Pass resort names to
`fetch` or `daily` to do a subset; both ignore resorts belonging to another
source.

## What's in the repo

| | |
|---|---|
| `resorts.json` | The resort registry — name, country, area, source, station. Source of truth. |
| `index.html` | Per-resort records. Generated — edit `template.html`. |
| `plan.html` | Multi-resort trip planner. Generated — edit `plan-template.html`. |
| `trends.html` | Season-by-season change per resort. Generated — edit `trends-template.html`. |
| `map.html` | Every snow-measuring station in Japan, mapped. Generated — edit `map-template.html`. |
| `*-template.html` | Markup for the three pages. `/*__DATA__*/null`, `/*__GROUPS__*/null`, `/*__SEASON__*/null` and `/*__TOTAL__*/0` are where the data lands. |
| `site.css`, `site.js` | Shared styling and shared behaviour — picker, date controls, stats, daily cache. Each page defines its own `renderPage()`. |
| `jma_snowfall.py` | The Japan fetcher: `discover`, `fetch`, `verify`, `daily`. Knows JMA and nothing else. |
| `site.py` | `build` — registry plus CSVs to HTML. Knows no weather service. |
| `data/*.csv` | One file per resort, one row per season. Generated. |
| `data/daily/*.json` | Daily new snow and snow depth, one file per station. Generated, cached. |
| `data/stations.json` | Annual snowfall for every station in the country that records it, plus the whole network's coordinates. Feeds the map. |
| `reference.json` | Resort elevations and claimed annual snowfall. |
| `fixtures/niseko_kutchan.csv` | The hand-transcribed Kutchan table. `verify` checks the scrape against it. |
| `seed_kutchan.py` | Prints that fixture to stdout: `python3 seed_kutchan.py > fixtures/niseko_kutchan.csv`. |

## Adding a country

`site.py` never opens a source-specific index or code table, so a second
country needs a fetcher and registry entries, not changes here.

1. Add entries to `resorts.json` with your own `source` and whatever `station`
   object your service needs.
2. Write a fetcher that produces, per resort, `data/<resort>.csv` with these
   columns: `resort, source, station, station_id, station_m, region, season,
   oct, nov, dec, jan, feb, mar, apr, may, season_total_cm, incomplete, note`.
   `station_m` may be blank. `season` is `YYYY/YY`.
3. Optionally write `data/daily/<source>-<station_id>.json`, keyed `"YYYY-MM"`,
   each holding `snow` and `depth` arrays of one value per day. Without it the
   resort appears on the records page but not the planner or trends.
4. Run `python3 site.py build`.

`station_id` need only be unique within a source — the daily filename is
namespaced, so two services may number stations however they like.

Two things are still Northern-hemisphere only. The season runs 1 Oct – 31 May
and is defined in one place (`SEASON_MONTHS` in `site.py`, emitted into each
page), but the season-year rule assumes a winter that straddles New Year, so a
Southern-hemisphere resort would need that generalised. And `verify` only
checks Japan; a second source should bring its own anchor.

## Reading the numbers

The element is 降雪の深さ月合計 — daily new-snow depth summed over the month. Not
snowpack depth (最深積雪), and not the cumulative figure resorts advertise.

JMA files snow by 寒候年, the cold-season year running 1 August to 31 July, so a
ski season spans two rows of the source table: October through December from
one calendar year, January through May from the next. Read the table naively
and every season total comes out wrong. The script handles it.

The season runs 1 October to 31 May — wider than Japan needs, so that the Alps
and the Rockies fit without migrating every stored file later. October and May
are simply near-zero at most Japanese stations.

Stations sit in the valley town, not on the mountain. Kutchan's station is about
a kilometre below the Niseko summit; Hakuba's is near the Happo base; Zao's is
down in Yamagata city. Compare a resort against its own history confidently,
against other resorts loosely. The site shows each station's elevation gap so
you can judge for yourself.

The Niseko series is validated against Ski Asia's published figures — 751 cm for
2025/26, 685 cm for 2019/20, 2,019 cm for 1969/70, 849 cm for the last-ten
average. All exact, and `verify` checks all 73 seasons against a hand
transcription on every run.

Those published figures are November to April, so they are what the site's
Nov–Apr columns sum to rather than its season total. Since the season widened
to October–May the two differ where October or May saw snow — 2025/26 is 751 cm
Nov–Apr and 752 cm across the full season. Across every Japanese resort October
contributes 0.21% of all recorded snowfall and May 0.16%; the columns are there
for the Alps and the Rockies, not for Japan.

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

## Adding a Japanese resort

One entry in `resorts.json` giving the station's exact Japanese name and its
region code. Grep `station_index.json` after `discover` to find it, and check
the station's `"snow"` flag is `true` — plenty of AMeDAS stations report wind
and temperature but no snow, and `fetch` will refuse rather than write an empty
series. Registry order is display order.

Data attribution in [ATTRIBUTION.md](ATTRIBUTION.md).
