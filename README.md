# Japan snowfall

Historical snowfall for Japanese ski resorts, taken from Japan Meteorological
Agency station records instead of resort marketing figures. A static site — no
build tooling, no dependencies, one Python script.

## Publish it

The repo is already initialised with one commit. Create an empty repo on GitHub
(no README, no .gitignore — this repo has both), then:

```bash
git remote add origin git@github.com:YOUR-USERNAME/japan-snowfall.git
git push -u origin main
```

Then **Settings → Pages → Source: Deploy from a branch**, branch `main`, folder
`/ (root)`. The site appears at
`https://YOUR-USERNAME.github.io/japan-snowfall/` within a minute or two.

## Fill in the other 28 resorts

Only Niseko has data committed. **Actions → Update snowfall data → Run
workflow.** GitHub's runners can reach `data.jma.go.jp`, so the scrape happens
there. First run takes about three minutes: it builds the station index, pulls
all 29 resorts, rebuilds `index.html`, and commits the result. After that it
runs itself every Monday from October through May.

If the workflow can't push, check **Settings → Actions → General → Workflow
permissions** is set to *Read and write*.

To run it locally instead:

```bash
python3 jma_snowfall.py discover
python3 jma_snowfall.py fetch
python3 jma_snowfall.py build
```

Standard library only.

## What's in the repo

| | |
|---|---|
| `index.html` | The site. Generated — edit `template.html` instead. |
| `template.html` | Markup and styling. `/*__DATA__*/null` is where the data lands. |
| `jma_snowfall.py` | `discover`, `fetch`, `build`. Resort-to-station mapping at the top. |
| `data/*.csv` | One file per resort, one row per season. |
| `reference.json` | Resort elevations and claimed annual snowfall. |
| `seed_kutchan.py` | The hand-transcribed Kutchan table, kept as a regression fixture. |

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
`RESORTS`.

**AMeDAS URLs are inferred.** Surface stations use `monthly_s3.php?view=p6`,
confirmed against Kutchan. Most resort stations are AMeDAS, whose equivalent
wasn't reachable during development, so `monthly_table()` tries several
script and view combinations and keeps whichever returns a table headed
降雪の深さの月合計値. If a resort fails, that's the first place to look.

**Station discovery** parses JMA's `viewPoint(...)` calls on the region maps. If
that markup changes there's a fallback that scrapes bare block numbers, but it
loses the station names, so `fetch` will then report stations missing.

Adding a resort means adding one line to `RESORTS` with the station's exact
Japanese name and its region code. Grep `station_index.json` after `discover` to
find it.

Data attribution in [ATTRIBUTION.md](ATTRIBUTION.md).
