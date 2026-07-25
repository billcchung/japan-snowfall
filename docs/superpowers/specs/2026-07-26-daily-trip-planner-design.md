# Day-resolution trip planner — design

Date: 2026-07-26

## Goal

Answer three questions the monthly data cannot:

1. What does a specific date range deliver — "25 Dec – 5 Jan", which crosses a
   month boundary and so cannot be expressed in whole-month buckets at all.
2. How much does it vary, so a window can be judged reliable or a coin flip.
3. How has it trended year over year.

## Source

JMA publishes daily tables at the same stations. Surface stations use
`view/daily_s1.php?year=&month=`, AMeDAS uses `view/daily_a1.php` — the same
split as the monthly tables, and `daily_a3.php` does not exist either.

Unlike the monthly tables these are a fixed width per station kind: 21 columns
for surface, 18 for AMeDAS, because an element the station does not measure
returns `///` rather than being omitted. 赤井川, which measures almost nothing
but snow, has the same 18 columns as 蘭越. Both wanted columns are at the end —
新雪 (降雪の深さ日合計) at `-4` and depth (最深積雪) at `-3` for surface, which
carries two trailing 天気概況 cells, versus `-2` and `-1` for AMeDAS.

Column identification is confirmed by reconciling daily sums against the
monthly totals already in the repo: 180 resort-months compared, zero
mismatches.

## Fetching and storage

`daily` fetches one station-month per request into
`data/daily/<prec>-<block>.json`, keyed `"YYYY-MM"` with parallel `snow` and
`depth` arrays. Cached months are skipped except the season in progress, which
JMA revises, so a cold start is ~2,900 requests and a weekly run is ~54.

Keyed by station rather than resort, so 旭川 is fetched once and serves both
Asahidake and Kamui — and the browser downloads it once for both.

The page fetches these files directly rather than the build emitting a second
per-resort copy, which would have duplicated 836 KB into the repo for nothing.
`build()` puts the station file id in each payload entry as `daily`.

## Day addressing

Days are an ordinal across Nov 1 – Apr 30, so a range crossing the New Year is
a contiguous slice and needs no special case. Month offsets use maximum month
lengths, which leaves slot 120 (29 Feb) empty in three seasons out of four;
`expectedDays()` discounts it so a non-leap season is not judged incomplete. A
season missing more than 20% of a window is excluded from that window's stats
rather than silently contributing a short total.

## Views

**Range result.** Mean, median, 10th–90th percentile, mean count of days at
20 cm or more, mean snow depth lying at the station, and best/leanest season.
Averaged over a selectable recent period, default 20 seasons — Niseko is down
about 25% from its first decade to its last, so a full-record mean oversells a
trip booked today.

**Season scan.** Holding the chosen trip length fixed, slide it across the
whole season and plot mean total against start date, with a 10th–90th band
whose width is the unreliability of that window. This is what makes the best
window visible instead of guessable; the range picker alone only grades a date
range the user already guessed.

**Year by year.** One column per season for the chosen window across the full
record, with a least-squares trend line. The scatter is the variability and the
line is the trend, so goals 2 and 3 share one chart.

## Verification

- Daily sums reconcile with committed monthly totals across all resorts.
- The planner's output for Niseko 25 Dec – 5 Jan recomputed independently in
  Python: mean 106 cm, median 118 cm, best 153 cm (2008/09), leanest 28 cm
  (2006/07) — matching the page exactly.
- No console errors; both charts render; resort switching reloads correctly.

## Note for future work

SVG `rect` takes `height` as a CSS property, so the existing `.bar` rule
(`height:7px`, for the matrix total bars) silently flattened the chart columns
until they were renamed `.col`. Watch for class-name collisions between HTML
and inline SVG.
