# Block Island Triathlon — Analysis Pipeline

Reproducible code behind the results site (`index.html`). Three scripts,
run in order, take the raw race-results spreadsheet all the way to the
live page.

```
Triathlon_Data_Full.xlsx
        │
        ▼  01_clean_data.py
triathlon_clean.csv            (2,953 rows — this is what's in the repo)
        │
        ▼  02_build_site_data.py
data_payload.json              (every derived stat/table the charts use)
        │
        ▼  03_update_html_data.py
index.html                     (swaps the embedded JSON, nothing else changes)
```

Verified: running all three against the original spreadsheet reproduces
the currently-published `index.html` byte-for-byte.

## Requirements

```
pip install pandas numpy openpyxl
```

No other dependencies for the Python side. The site itself pulls
Chart.js from a CDN at load time (`cdnjs.cloudflare.com`); there's no
build step and no server — `index.html` is a single self-contained file.

## 1. `01_clean_data.py`

```
python 01_clean_data.py Triathlon_Data_Full.xlsx triathlon_clean.csv
```

Reverses two Excel autocorrect corruptions in the source file (place/total
fractions like "15/48" getting read as dates; split times like "31:10"
getting read as 31 hours instead of 31 minutes), then removes rows that
were never usable individual results (relay teams, a disqualification, a
few rows too incomplete to reconstruct). Full narrative writeup of *why*
each fix works is in the code comments and in `cleaning_notes.md`.

Every step prints its row count, so you can see exactly where rows drop:
2,972 raw → 2,953 final.

## 2. `02_build_site_data.py`

```
python 02_build_site_data.py triathlon_clean.csv data_payload.json
```

One function per site section — the docstring on each explains what it
feeds and any non-obvious modeling choice (e.g. why the age-vs-time trend
line uses a 5-year rolling average, or why "what determines your place"
is a variance decomposition rather than a naive regression). Look here
first if you want to understand or change any specific chart's logic.

Sections marked "legacy" in the code (`overall_pace`, `perfect_attendance`,
`top_fastest`, `heatmap`, and `agegroup_stats`'s `pct_bucket`/`bucket_order`)
were used by earlier iterations of the site and are no longer rendered, but
are still computed and included in the payload since removing them wasn't
asked for.

The most recently added section, `build_tier_by_year`, powers "Where the
field actually separates" — a radar chart comparing Top 5/25/100/200
finishers' swim/bike/run pace. It went through two earlier designs before
landing here (first grouped by age+sex, then by age alone) because small
age or sex subgroups have few enough people per season that a cutoff like
"Top 100" can silently become identical to "Top 200" once the cutoff
exceeds how many people even exist in a given season -- there just aren't
100 people to choose from some years. The final version drops age entirely
and offers year (optional) and gender (optional) as the only filters, and
the site's own UI detects and explains it in the rarer case where a single
small-field season + gender combination still hits that same edge case.

## 3. `03_update_html_data.py`

```
python 03_update_html_data.py index.html data_payload.json index.html
```

Finds the `<script id="data-payload" type="application/json">` tag in
`index.html` and replaces its contents with a fresh payload, leaving
every other line of the file untouched. This is how you'd push a new
season's results: append the new rows to the raw spreadsheet, rerun all
three scripts, redeploy the resulting `index.html`.

## Where the chart code lives

There's no separate JS/chart file — all of it is inline in `index.html`,
in the plain (non-JSON) `<script>` tag right after the data payload. It's
organized as one IIFE per site section, in the same top-to-bottom order
the sections appear on the page (hero wave → pace chart → year-over-year
comparison → leg breakdown → age groups → tiers → impact regression →
records → bump chart → heatmap → age scatter → galaxy → featured racers →
explorer table). Each IIFE reads its slice of `DATA` and renders directly
into the DOM — nothing is minified or built, so it reads the same in the
browser's dev tools as it does in the source file.
