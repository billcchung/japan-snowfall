# Multi-resort planner, page split, and resort registry — design

Date: 2026-07-26

## Goals

1. Compare several resorts over one date range, to answer "where should I go —
   and if none of these look good, should I be looking at another area?"
2. Move the planner off the records page.
3. Group resorts by area in a way that survives adding other countries.

## Registry

`resorts.json` replaces the `RESORTS` table as the source of truth. Each entry
carries `name`, `country`, `area`, `source`, `station` and `note`. Area is now
an explicit property rather than being derived from a JMA prefecture code,
which has no meaning outside Japan.

`jma_snowfall.py` becomes the Japan adapter: it claims only entries whose
`source` is `jma`. Adding a country means new entries plus a fetcher writing
the same per-resort CSV and the same `data/daily/` cache shape. `build()`
groups the picker country → area → resort and prints the country prefix only
when more than one exists, so the hierarchy is in place without cluttering a
single-country site.

This also removes the `LABEL` map, which had been silently gating which
resorts could render — a resort with data but no label entry never appeared.

## Two pages

`index.html` keeps the per-resort record: station provenance, stat tiles,
month heatmap. It no longer loads any daily data. `plan.html` holds the
planner. Shared styling moves to `site.css`; page-specific rules stay inline in
each template. `build()` renders both from `template.html` and
`plan-template.html`, substituting `/*__DATA__*/null`, `/*__GROUPS__*/null` and
`/*__TOTAL__*/0`.

## Comparison

Selected resorts are ranked by median snowfall over the chosen window,
alongside the 10th–90th percentile, standard deviation as both an absolute and
a share of typical, powder days, base depth, and whether a different window
would do better at that resort.

Two charts:

- **When to go** — season-scan curves overlaid on shared axes, so it is visible
  at a glance when every selected resort peaks away from the chosen dates. Each
  line carries its own 10th–90th percentile band, so spread is read in the same
  place as level: a fat band is a lottery, a tight one is dependable.

  Multiple bands were first assumed to be unreadable and replaced with a
  box-and-whisker panel. That was wrong on both counts — the boxes divorced
  spread from the date axis, which is the whole question, and the bands are
  legible with three things done: fills use `mix-blend-mode: screen`, so on a
  dark ground overlaps brighten instead of muddying the way plain alpha
  compositing does; every band is drawn before any mean line, so no fill ever
  covers a line; and fill opacity scales as `0.24 / n^0.45`, keeping one resort
  rich and six readable. Band edges are smoothed over a 7-point window because
  each start date draws on only ~20 seasons and the wobble is sampling noise;
  the mean line stays exact so the peak marker remains honest. A Spread toggle
  turns the bands off.
- **Year by year** — one line per resort across the full record, plus each
  resort's linear trend.

The chart key toggles series visibility. Hidden series drop out of both
charts but stay in the table, dimmed, so the comparison is never silently
incomplete.

Daily files are cached per station, so resorts sharing a station download once.
The default selection skips a resort that would repeat an already-chosen
station, since two identical rows reads as a bug rather than a fact.

## Defects found in review and fixed

**Unresolvable station.** `lotte-arai` pointed at `新井`, which does not exist
anywhere in JMA's 1,302-station index. `fetch` logged to stderr and continued,
so the workflow would have gone green while the resort silently vanished from
every page. Repointed at `関山` (350 m, against a 330 m resort base) and
`fetch` now exits non-zero on an unresolved station, because that is always a
registry typo rather than a transient failure.

**Verdict asserted a direction it never checked.** The summary said every
resort "peaks later than your window" whenever the peak was merely better.
Rusutsu peaks three days *earlier* than the default window, so the page stated
a falsehood. It now tests the direction and says later, earlier, or
"somewhere other than" for a mixed set.

## Note

SVG `rect` takes `height` as a CSS property, so the existing `.bar` rule
(`height:7px`, for the matrix total bars) silently flattened chart columns
until they were renamed `.col`. Watch for class-name collisions between HTML
and inline SVG.
