# Triathlon Data Cleaning Notes

**Source:** Triathlon_Data_Full.xlsx (2016–2025, excl. 2020) — 2,972 racer-results rows.

## Issues found & fixed

**1. PLC/TOT (division place/total), e.g. "15-Jan" or "Jan-48"**
Excel auto-converted "PLACE/TOTAL" text (e.g. "1/15") into a date, since a number ≤12
looks like a month. Reconstructed as:
- Plain string like "14/48" → already safe (PLACE was >12, so Excel couldn't convert it) → split on "/"
- Date with year ≥ 2000 → PLACE = month, TOTAL = day
- Date with year < 2000 → PLACE = month, TOTAL = (year − 1900)  [Excel's 2-digit-year fallback for invalid "day" values >31]
- 2 rows (Feb 29 edge case) manually corrected to Place=2 using surrounding-row context.

**2. Split times (swim/T1/bike/T2/run), e.g. "31:10:00" for a bike split**
Times entered as "MM:SS" (e.g. "31:10") were auto-interpreted by Excel as "H:MM"
(31 hours, 10 min), which for splits ≥24h rolled into a multi-day duration.
Correction: divide the corrupted total by 60 — UNLESS the cell already had a nonzero
seconds component, which means it was a genuine "H:MM:SS" entry (some very slow
run/bike splits legitimately exceed 60 minutes).

**3. 13 rows with a leftover ~60-second placeholder on bike or run**
After the above fix, splits still didn't sum to the recorded finish time for 13 rows.
In each case, exactly one leg (bike or run) showed an implausible ~60-65 second split —
almost certainly a timing-mat glitch in the *original* race results, not a paste error.
Backfilled using: true_split = FinishTime − (sum of other 4 known-good legs).

**4. Non-errors, left as-is**
- `CITY` containing "==========" → runner opted out of showing location (159 rows) → set to null, flagged `CityRedacted`
- `VE` (Wave) → start wave codes 1–9, A–F, not an error
- 16 `Name` entries with RELAY/DQ/DNB/no-swim annotations → extracted into `NameFlag`, name text cleaned
- A handful of "--" split values → genuine DNS on that leg, left null

## Output
`triathlon_clean.csv` — 25 columns, tidy one-row-per-racer-result, ready for analysis/viz.
