# Data attribution

**Snowfall and snow depth** — Japan Meteorological Agency, 過去の気象データ検索
(https://www.data.jma.go.jp/stats/etrn/). Elements: 降雪の深さ月合計 and
降雪の深さ日合計, the sum of daily new-snow depth in centimetres over a month and
over a day, plus 最深積雪, the depth lying on the ground, used by the trip
planner. JMA publishes its observation data for reuse; keep the attribution
visible, which both page footers do. JMA revises historical values
retrospectively, so figures here are current as of the last workflow run, not
permanent.

**Resort elevations and claimed annual snowfall** — Powderhounds, "Japan ski
resort statistics comparison". Used in `reference.json` for context only. The
claimed figures are resort marketing numbers and are not observations; they are
shown on the site precisely so the gap against the station record is visible.
Resorts added after that source was compiled carry null elevations rather than
figures from an unnamed source — null there means not looked up, not zero.

**Validation reference** — Ski Asia's Niseko snowfall page
(https://skiasia.com/snowfall/niseko/) was used to check that this project reads
JMA's cold-season tables correctly. No data was copied from it.

The code in this repository is yours to do what you like with. The observation
data belongs to JMA.
