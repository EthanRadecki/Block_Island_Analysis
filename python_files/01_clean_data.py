"""
Block Island Triathlon — Data Cleaning Pipeline
=================================================
Input:  Triathlon_Data_Full.xlsx (raw results, 2016-2025, no 2020 race)
Output: triathlon_clean.csv (2,953 rows, one row per finisher-result)

The source spreadsheet has two independent Excel autocorrect corruptions
that this script reverses, plus a handful of one-off data-quality issues
(relay entries, DQs, unrecoverable rows) that get flagged and removed.
See cleaning_notes.md alongside this file for the full narrative writeup;
this script is the executable version of that same logic.

Usage:
    pip install pandas numpy openpyxl
    python 01_clean_data.py /path/to/Triathlon_Data_Full.xlsx
"""
import sys
import re
import datetime
import numpy as np
import pandas as pd

INPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else 'Triathlon_Data_Full.xlsx'
OUTPUT_PATH = sys.argv[2] if len(sys.argv) > 2 else 'triathlon_clean.csv'


# ============================================================
# 1. PLC/TOT (division place / division total) reconstruction
# ============================================================
# Original values were text like "15/48" (place 15 of 48). Because a number
# <=12 looks like a month, Excel silently converted many of these into dates:
#   - text like "14/48" (place > 12) -> safe, Excel left it as a string
#   - a date with year >= 2000       -> PLACE = month, TOTAL = day
#   - a date with year <  2000       -> PLACE = month, TOTAL = (year - 1900)
#     (this is Excel's fallback when the "day" component, e.g. 48, is > 31
#     and invalid, so it reinterprets the pair as a month/2-digit-year)
def recon_plc_tot(v):
    if isinstance(v, str):
        try:
            p, t = v.split('/')
            return int(p), int(t)
        except Exception:
            return np.nan, np.nan
    if isinstance(v, datetime.datetime):
        if v.year >= 2000:
            return v.month, v.day
        return v.month, v.year - 1900
    return np.nan, np.nan


# ============================================================
# 2. Split times (swim / T1 / bike / T2 / run) reconstruction
# ============================================================
# Times entered as "MM:SS" (e.g. "31:10") were auto-interpreted by Excel as
# "H:MM" (31 hours, 10 minutes). For splits >= 24h this rolls into a
# multi-day duration (a datetime.timedelta). For splits < 24h it stays a
# datetime.time object with the true minutes/seconds sitting in the
# hour/minute slots instead, and seconds == 0.
#
# The fix in both cases: divide the corrupted total by 60. The one
# exception is when a cell's "seconds" component is nonzero -- that means
# it was typed as a genuine 3-part "H:MM:SS" (some very slow finishers
# really do have run/bike splits over an hour), so it's already correct
# and is left alone.
def parse_split(v):
    if pd.isna(v):
        return np.nan
    if isinstance(v, str):
        s = v.strip()
        if s in ('--', ''):
            return np.nan
        try:
            parts = [int(p) if p != '' else 0 for p in s.split(':')]
        except ValueError:
            return np.nan
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
        return np.nan
    if isinstance(v, datetime.timedelta):
        return v.total_seconds() / 60.0
    if isinstance(v, datetime.time):
        h, m, s = v.hour, v.minute, v.second
        if s == 0:
            return float(h * 60 + m)          # corrupted 2-part H:MM -> true M:SS
        return float(h * 3600 + m * 60 + s)   # genuine 3-part H:MM:SS, kept as-is
    return np.nan


def parse_finish(v):
    """Overall finish TIME column is genuinely H:MM:SS -- no correction needed."""
    if isinstance(v, datetime.time):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, datetime.timedelta):
        return v.total_seconds()
    return np.nan


def split_age_sex(v):
    """A/S column looks like '44M' or '21F' -> (44, 'M')."""
    m = re.match(r'^(\d+)([MF])$', str(v).strip())
    if m:
        return int(m.group(1)), m.group(2)
    return np.nan, np.nan


def name_flag(n):
    """Detect relay/DQ/DNB/no-swim/other annotations embedded in the Name field."""
    n = str(n)
    if re.search(r'relay', n, re.I):
        return 'RELAY'
    if re.search(r'\bDQ\b', n):
        return 'DQ'
    if re.search(r'DNB', n):
        return 'DNB'
    if re.search(r'no swim', n, re.I):
        return 'NO_SWIM'
    if re.search(r'\*D\*', n):
        return 'D_FLAG'
    if re.search(r'\*\*', n):
        return 'FLAGGED'
    return None


def sec_to_hms(s):
    if pd.isna(s):
        return np.nan
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


LEG_COLS = ['SwimSec', 'T1Sec', 'BikeSec', 'T2Sec', 'RunSec']


def main():
    df = pd.read_excel(INPUT_PATH, header=1)
    print(f"Loaded {len(df)} raw rows from {INPUT_PATH}")

    # ---- PLC/TOT ----
    plc = df['PLC/TOT'].apply(recon_plc_tot)
    df['DivPlace'] = plc.apply(lambda x: x[0])
    df['DivTotal'] = plc.apply(lambda x: x[1])
    # Two rows hit a Feb-29 rollover Excel couldn't represent in a non-leap
    # default year (produced day=1 instead of day=29). Fixed using the
    # surrounding place sequence in that division: both are place 2 of 29.
    mask_feb29 = df['PLC/TOT'].apply(
        lambda v: isinstance(v, datetime.datetime) and v.month == 2 and v.day == 1 and v.year >= 2027
    )
    df.loc[mask_feb29, ['DivPlace', 'DivTotal']] = [2, 29]

    # ---- Split times ----
    split_map = {'SPLIT': 'SwimSec', 'SPLIT.1': 'T1Sec', 'SPLIT.2': 'BikeSec',
                 'SPLIT.3': 'T2Sec', 'SPLIT.4': 'RunSec'}
    for col, new in split_map.items():
        df[new] = df[col].apply(parse_split)
    df['FinishSec'] = df['TIME'].apply(parse_finish)

    # A handful of rows still won't sum to the recorded finish time after the
    # above fix -- in each case exactly one leg (bike or run) shows an
    # implausible ~60-second placeholder, almost certainly a timing-mat
    # glitch in the *original* results. Back-calculate the true value from
    # the finish time and the four other known-good legs.
    sum_parts = df[LEG_COLS].sum(axis=1, min_count=5)
    diff = (sum_parts - df['FinishSec']).abs()
    for idx in df.index[diff > 10]:
        row = df.loc[idx]
        candidates = {c: row[c] for c in ['BikeSec', 'RunSec']}
        suspect_col = min(candidates, key=lambda k: candidates[k])
        others_sum = sum(row[c] for c in LEG_COLS if c != suspect_col)
        df.at[idx, suspect_col] = row['FinishSec'] - others_sum

    # ---- Renames ----
    df = df.rename(columns={
        'RANK': 'SwimRank', 'RANK.1': 'T1Rank', 'RANK.2': 'BikeRank',
        'RANK.3': 'T2Rank', 'RANK.4': 'RunRank', 'PLC': 'OverallPlace',
        'VE': 'Wave', 'BIB': 'Bib', 'DIV': 'DivCode',
    })

    # ---- Age / Sex ----
    age_sex = df['A/S'].apply(split_age_sex)
    df['Age'] = age_sex.apply(lambda x: x[0])
    df['Sex'] = age_sex.apply(lambda x: x[1])

    # ---- City redaction ----
    # "==========" means the entrant opted out of showing their city in the
    # original results -- that's a genuine privacy choice, not an error.
    df['City'] = df['CITY'].apply(lambda x: np.nan if isinstance(x, str) and '==========' in x else x)
    df['CityRedacted'] = df['CITY'].apply(lambda x: isinstance(x, str) and '==========' in x)

    # ---- Name flags (relay / DQ / DNB / no-swim / ambiguous asterisk notes) ----
    df['NameFlag'] = df['Name'].apply(name_flag)
    df['Name'] = df['Name'].apply(lambda n: re.sub(r'\s*[\*\(].*', '', str(n)).replace('RELAY', '').strip())

    df['FinishTimeStr'] = df['FinishSec'].apply(sec_to_hms)

    keep_cols = ['Year', 'OverallPlace', 'Name', 'NameFlag', 'Age', 'Sex', 'DivCode',
                 'DivPlace', 'DivTotal', 'City', 'CityRedacted',
                 'FinishSec', 'FinishTimeStr',
                 'SwimRank', 'SwimSec', 'T1Rank', 'T1Sec', 'BikeRank', 'BikeSec',
                 'T2Rank', 'T2Sec', 'RunRank', 'RunSec', 'Wave', 'Bib']
    df = df[keep_cols].copy()
    print(f"After reconstruction: {len(df)} rows")

    # ============================================================
    # 3. Remove rows that were never usable individual results
    # ============================================================
    # 3a. Relay teams, disqualifications, DNB, no-swim, and ambiguous
    #     asterisk-flagged rows -- these were kept-but-flagged in an earlier
    #     pass, but the project has no use for them.
    before = len(df)
    df = df[df['NameFlag'].isna()].drop(columns=['NameFlag']).reset_index(drop=True)
    print(f"Dropped {before - len(df)} relay/DQ/DNB/flagged rows -> {len(df)} rows")

    # 3b. Two more relay-style entries slipped through because they had no
    #     text annotation -- division code "M0000"/"F0000" with Age==0 is
    #     not a real individual racer.
    before = len(df)
    df = df[~df['DivCode'].isin(['M0000', 'F0000'])].reset_index(drop=True)
    print(f"Dropped {before - len(df)} age-0 relay-coded rows -> {len(df)} rows")

    # 3c. A few rows are missing exactly one leg's time (the original results
    #     had "--" for that leg only, but a valid overall finish time).
    #     Back-solve the single missing leg from the finish time and the
    #     four known legs. If two or more legs are missing there isn't
    #     enough information to solve for both, so that row is dropped.
    unfixable = []
    for idx, row in df.iterrows():
        missing = [c for c in LEG_COLS if pd.isna(row[c])]
        if len(missing) == 1:
            col = missing[0]
            others_sum = sum(row[c] for c in LEG_COLS if c != col)
            df.at[idx, col] = row['FinishSec'] - others_sum
        elif len(missing) > 1:
            unfixable.append(idx)
    df = df.drop(index=unfixable).reset_index(drop=True)
    print(f"Backfilled single-missing-leg rows; dropped {len(unfixable)} unsolvable row(s) -> {len(df)} rows")

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(df)} rows x {len(df.columns)} columns -> {OUTPUT_PATH}")
    print(f"Missing values remaining (City is expected -- privacy opt-outs):")
    print(df.isna().sum()[df.isna().sum() > 0])


if __name__ == '__main__':
    main()
