# Hokkaido expansion — design

Date: 2026-07-25

## Goal

Publish the site to GitHub Pages with real data for all ten Hokkaido resorts
already mapped in `RESORTS`. Today only Niseko has data, and the scraper cannot
fetch the other nine.

## Why it does not work today

`monthly_table()` guesses at the AMeDAS URL. It tries `monthly_a3.php`, which
returns HTTP 404 for every station, then falls back to `monthly_s3.php`, which
returns a page without the snowfall table. All ten script/view combinations in
`SCRIPTS`/`CODES` are dead ends, so every AMeDAS resort raises
`RuntimeError("no snowfall table")` and is skipped.

Verified against live JMA:

- Surface stations expose `view/monthly_s3.php` — every year in one request,
  snowfall under `view=p6`. This path is correct and already works.
- AMeDAS stations expose no monthly-matrix script at all. Their station index
  offers only `annually_a.php`, `nml_amd_*`, `rank_a.php`. The working monthly
  endpoint is `view/monthly_a1.php?year=YYYY`, one calendar year per request.

Of the ten Hokkaido resorts, three sit on surface stations (倶知安 47433,
札幌 47412, 旭川 47407) and six on AMeDAS (蘭越 0055, 喜茂別 0060, 赤井川 1091,
富良野 0021, 占冠 1189, 新得 0113). All nine report `f_snc=1`, so all measure
snow. Asahidake and Kamui share 旭川.

## Changes

### 1. Two fetch paths instead of one guess

Replace `SCRIPTS`/`CODES` brute force with an explicit branch on station kind.

`monthly_surface()` keeps the current logic: one request, parse rows whose
first cell is a 4-digit year, take cells 1..12 as calendar months.

`monthly_amedas()` reads available years from
`index.php?prec_no=&block_no=`, which lists one link per year of record, then
requests `monthly_a1.php?year=YYYY` for each. Each response is a 12-row table,
one row per calendar month.

Column position is **not** hardcoded. Station tables vary in width because
stations that skip wind, temperature, or sunshine emit fewer columns. The three
snow columns are always last and always in the order 降雪の深さ 合計(cm),
降雪の深さ 日合計の最大(cm), 最深積雪(cm), so snowfall is read from `cells[-3]`
after asserting the row carries a plausible column count.

### 2. Fetch per station, not per resort

Ten resorts map to nine stations. Group `RESORTS` by `(prec_no, station_ja)`,
fetch each station once, write a CSV per resort from the shared result. Without
this, 旭川 is scraped twice — which was cheap when that meant one request and
is not once AMeDAS means fifty.

### 3. Seed file stops shadowing fresh data

`data/niseko_kutchan.csv` has a different filename convention and a different
column schema from what `fetch` writes, but its `resort` column says `niseko`.
`build()` walks `data/` alphabetically, so `niseko_kutchan.csv` sorts after
`niseko.csv` and silently overwrites the fresh scrape in the payload.

Move it to `fixtures/niseko_kutchan.csv` and add a `verify` subcommand that
compares the scraped Kutchan series against it season by season, exiting
non-zero on mismatch. This preserves the four validated Ski Asia figures
(751 cm for 2025/26, 685 cm for 2019/20, 2019 cm for 1969/70, 849 cm ten-year
average) as an actual assertion rather than a comment in the README.

### 4. Region reaches the front end

`build()` currently drops `prec_no`, so nothing downstream knows where a resort
is. Emit `region` (the subprefecture or prefecture name) and `area` (the coarse
grouping: Hokkaido, Tohoku, Niigata/Nagano, Other) into each payload entry,
derived from `prec_no` via a new `AREA` mapping.

### 5. Picker groups by area, and stops being an allowlist

`ALL = Object.keys(LABEL)` means a resort with committed data but no `LABEL`
entry silently never renders. Drive the picker from the payload instead, using
`LABEL` only for display names and falling back to a title-cased key. Group
buttons under area headings with Hokkaido first.

### 6. Two small robustness fixes

`fetch()` does `csv.DictWriter(f, fieldnames=list(rows[0].keys()))` unguarded,
so a station returning zero seasons aborts the entire run with `IndexError`
rather than skipping that one resort. Guard it.

`to_seasons()` writes an `incomplete` flag that nothing reads, so partial
seasons render as confident totals. Carry it into the payload and mark those
seasons in the UI.

## Out of scope

Adding Hokkaido resorts beyond the ten already mapped. Removing the nineteen
Honshu resorts. Both are follow-on decisions once real data exists.

## Verification

- `verify` passes against the hand-transcribed Kutchan fixture.
- All ten Hokkaido resorts produce a CSV with a plausible season count.
- `index.html` renders ten Hokkaido resorts grouped under a Hokkaido heading.
- The published Pages URL serves that page.
