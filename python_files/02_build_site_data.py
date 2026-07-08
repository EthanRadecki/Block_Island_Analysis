"""
Block Island Triathlon — Site Data Builder
============================================
Input:  triathlon_clean.csv (output of 01_clean_data.py)
Output: data_payload.json -- every derived table/statistic the website's
        charts consume, as one JSON object. The site (index.html) embeds
        this JSON directly in a <script type="application/json"> tag and
        all charts/tables read from it client-side; nothing is computed
        server-side or fetched at runtime.

Usage:
    pip install pandas numpy
    python 02_build_site_data.py /path/to/triathlon_clean.csv
"""
import sys
import json
import numpy as np
import pandas as pd

INPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else 'triathlon_clean.csv'
OUTPUT_PATH = sys.argv[2] if len(sys.argv) > 2 else 'data_payload.json'

LEGS = ['SwimSec', 'T1Sec', 'BikeSec', 'T2Sec', 'RunSec']

FEATURED_NAMES = ['Eric Radecki', 'Hunter Radecki', 'Jack Kenyon',
                  'Ethan Radecki', 'Carmine Pittelli', 'Michael Radecki']


def age_group(a):
    """The single age-bucketing scheme used everywhere on the site: the
    age-group bar chart, the heatmap, the galaxy view, and the explorer's
    age-group filter all call this exact function so the buckets always
    line up with each other."""
    if a < 20: return '0-19'
    if a < 25: return '20-24'
    if a < 30: return '25-29'
    if a < 35: return '30-34'
    if a < 40: return '35-39'
    if a < 45: return '40-44'
    if a < 50: return '45-49'
    if a < 55: return '50-54'
    if a < 60: return '55-59'
    if a < 65: return '60-64'
    if a < 70: return '65-69'
    return '70+'


AGE_ORDER = ['0-19', '20-24', '25-29', '30-34', '35-39', '40-44',
             '45-49', '50-54', '55-59', '60-64', '65-69', '70+']


def build_yearly(df):
    """'Finish times by year' line chart + hero stat cards."""
    g = df.groupby('Year').agg(
        count=('Name', 'count'), avg_finish=('FinishSec', 'mean'),
        median_finish=('FinishSec', 'median'), fastest=('FinishSec', 'min'),
        pct_female=('Sex', lambda s: round(100 * (s == 'F').mean(), 1)),
        avg_age=('Age', 'mean'),
    ).round(1).reset_index()
    return g.to_dict(orient='records')


def build_pace_by_year(df):
    """'Are some years just faster?' section, and the swim/bike/run
    year-over-year comparison (bike is the fixed-distance control leg)."""
    g = df.groupby('Year')[LEGS].mean().round(1)
    return [{'year': int(y), 'swim': r.SwimSec, 't1': r.T1Sec, 'bike': r.BikeSec,
             't2': r.T2Sec, 'run': r.RunSec} for y, r in g.iterrows()]


def build_overall_pace(df):
    """Legacy: originally powered the (now-filterable) 'Where the clock
    goes' section before that section was rebuilt to compute live from
    `explorer` client-side. Kept for reference; unused by the current UI."""
    return {k: round(v, 1) for k, v in df[LEGS].mean().items()}


def build_records_by_year(df):
    """Course records section: fastest man/woman per season."""
    records = []
    for y, g in df.groupby('Year'):
        entry = {'year': int(y)}
        for sex in ['M', 'F']:
            gg = g[g['Sex'] == sex]
            if len(gg):
                r = gg.loc[gg['FinishSec'].idxmin()]
                entry[sex] = {'name': r['Name'], 'time': r['FinishTimeStr'], 'sec': int(r['FinishSec'])}
        records.append(entry)
    return records


def build_top_fastest(df):
    """Not currently rendered as its own section (superseded by the
    records-by-year table + explorer), kept for reference."""
    return df.nsmallest(15, 'FinishSec')[['Year', 'Name', 'Age', 'Sex', 'DivCode', 'FinishTimeStr']].to_dict(orient='records')


def build_perfect_attendance(df):
    """Legacy: originally its own 'Perfect Attendance' section, removed
    per feedback that it wasn't needed. Kept here for reference."""
    n_years = df['Year'].nunique()
    attendance = df.groupby('Name')['Year'].nunique()
    perfect_names = attendance[attendance == n_years].index.tolist()
    out = []
    for name in perfect_names:
        g = df[df['Name'] == name].sort_values('Year')
        out.append({'name': name, 'years': g[['Year', 'FinishTimeStr', 'FinishSec', 'OverallPlace']].to_dict(orient='records')})
    return out


def build_age_scatter(df):
    """'Age vs. finish time' scatter -- every finisher, one point each."""
    return df[['Age', 'Sex', 'FinishSec', 'Name', 'Year', 'DivCode']].dropna(subset=['Age']).to_dict(orient='records')


def build_age_trend(df):
    """The solid average-by-age line overlaid on the scatter. Uses a
    5-year centered rolling average (not the raw per-age mean) because
    sample size per single age drops into single digits past ~63 and
    to 1-3 people past 70, which makes the raw per-age average zig-zag
    noisily. min_periods=1 so the ends of the age range still get a value."""
    trend = df.groupby(['Age', 'Sex'])['FinishSec'].mean().reset_index()
    out = {}
    for sex in ['M', 'F']:
        sub = trend[trend.Sex == sex].sort_values('Age').set_index('Age')['FinishSec']
        smoothed = sub.rolling(window=5, center=True, min_periods=1).mean()
        out[sex] = [{'age': int(age), 'avg': round(val / 60, 1)} for age, val in smoothed.items()]
    return out


def build_explorer(df):
    """The full searchable/sortable results table at the bottom of the
    site. Every row here also gets a live-computed performance color
    (green=faster, red=slower) client-side -- that coloring is NOT
    precomputed here, it's recalculated in the browser based on
    whatever year/sex/age-group filter is currently active."""
    cols = ['Year', 'OverallPlace', 'Name', 'Age', 'Sex', 'DivCode', 'DivPlace', 'DivTotal',
            'City', 'FinishTimeStr', 'FinishSec', 'SwimSec', 'T1Sec', 'BikeSec', 'T2Sec', 'RunSec']
    out = df[cols].copy()
    out['City'] = out['City'].fillna('')
    return out.to_dict(orient='records')


def build_meta(df):
    return {
        'total_results': len(df),
        'years': sorted(df['Year'].unique().tolist()),
        'n_years': df['Year'].nunique(),
        'unique_racers': df['Name'].nunique(),
    }


def build_agegroup_stats(df):
    """'Average time by age group' bar chart + 'Average time by finishing
    tier' chart. Tiers are percentile-of-that-year's-own-field, not raw
    place, because field size ranged from 230 to 429 across seasons --
    percentile keeps the comparison fair across years."""
    df = df.copy()
    df['AgeGroup'] = df['Age'].apply(age_group)

    agegroup_stats = df.groupby(['AgeGroup', 'Sex']).agg(
        n=('Name', 'count'), avg_finish=('FinishSec', 'mean'),
        avg_swim=('SwimSec', 'mean'), avg_bike=('BikeSec', 'mean'), avg_run=('RunSec', 'mean'),
    ).reset_index()
    agegroup_json = []
    for ag in AGE_ORDER:
        row = {'group': ag}
        for sex in ['M', 'F']:
            sub = agegroup_stats[(agegroup_stats.AgeGroup == ag) & (agegroup_stats.Sex == sex)]
            if len(sub):
                r = sub.iloc[0]
                row[sex] = {'n': int(r.n), 'avg_finish': round(r.avg_finish, 1), 'avg_swim': round(r.avg_swim, 1),
                            'avg_bike': round(r.avg_bike, 1), 'avg_run': round(r.avg_run, 1)}
        agegroup_json.append(row)

    df['FieldSize'] = df.groupby('Year')['Name'].transform('count')
    df['PctPlace'] = 100 * df['OverallPlace'] / df['FieldSize']

    def pct_bucket(p):
        if p <= 10: return 'Top 10%'
        if p <= 25: return 'Top quarter (11\u201325%)'
        if p <= 50: return 'Upper half (26\u201350%)'
        if p <= 75: return 'Lower half (51\u201375%)'
        return 'Back of pack (76\u2013100%)'
    df['PctBucket'] = df['PctPlace'].apply(pct_bucket)
    bucket_order = ['Top 10%', 'Top quarter (11\u201325%)', 'Upper half (26\u201350%)',
                     'Lower half (51\u201375%)', 'Back of pack (76\u2013100%)']
    pct_stats = df.groupby('PctBucket').agg(
        n=('Name', 'count'), avg_finish=('FinishSec', 'mean'),
        avg_swim=('SwimSec', 'mean'), avg_bike=('BikeSec', 'mean'), avg_run=('RunSec', 'mean'),
    ).reindex(bucket_order).reset_index()

    return {
        'age_order': AGE_ORDER,
        'agegroup': agegroup_json,
        'bucket_order': bucket_order,
        'pct_bucket': pct_stats.round(1).to_dict(orient='records'),
    }


def build_regression(df):
    """'What actually determines your place' section. Two complementary
    views of the same idea, both driven off the same variance-decomposition
    number (this matters -- an earlier version of this chart accidentally
    sized the bars off the regression coefficients while labeling them
    with the variance-decomposition percentages, which don't move in
    lockstep, so the bar lengths silently disagreed with their own labels):

      1. Variance decomposition: Cov(leg, total) / Var(total) for each leg.
         These five numbers sum to ~1 exactly (a property of Var(sum) for
         any set of variables), and answer "how much of the *spread*
         between racers' finish times traces back to this leg" -- which is
         different from "how long does this leg take" (a long leg with low
         variance across racers won't separate anyone's placement much).
      2. A standardized linear regression of each racer's placement
         percentile (0=first place, 100=last, computed within their own
         year to normalize for different field sizes) on each leg's time,
         z-scored within year. Comparing standardized-beta magnitudes is
         only valid because all predictors are on the same standardized
         scale.
    """
    total = df[LEGS].sum(axis=1)
    var_total = total.var()
    variance_decomp = {leg: round(100 * df[leg].cov(total) / var_total, 1) for leg in LEGS}

    df = df.copy()
    df['FieldSize'] = df.groupby('Year')['Name'].transform('count')
    df['PctPlace'] = 100 * df['OverallPlace'] / df['FieldSize']

    z = df.copy()
    for leg in LEGS:
        z[leg + '_z'] = z.groupby('Year')[leg].transform(lambda s: (s - s.mean()) / s.std())
    X = z[[l + '_z' for l in LEGS]].values
    X = np.column_stack([np.ones(len(X)), X])
    y = z['PctPlace'].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    return {
        'variance_decomp': variance_decomp,
        'regression_coef': {leg: round(c, 3) for leg, c in zip(LEGS, coef[1:])},
        'r2': round(r2, 3),
        'correlations': {leg: round(df[leg].corr(z['PctPlace']), 3) for leg in LEGS},
    }


def build_bump(df):
    """'How rankings shift during the race' section. For each year: that
    season's top 5 overall finishers, plus any of the featured racers who
    raced that year (deduplicated), each with their rank right after the
    swim, right after the bike, and at the finish."""
    bump = {}
    for y, g in df.groupby('Year'):
        g = g.copy()
        g['t_swim'] = g['SwimSec']
        g['t_bike'] = g['SwimSec'] + g['T1Sec'] + g['BikeSec']
        g['t_finish'] = g['FinishSec']
        g['r_swim'] = g['t_swim'].rank(method='min').astype(int)
        g['r_bike'] = g['t_bike'].rank(method='min').astype(int)
        g['r_finish'] = g['t_finish'].rank(method='min').astype(int)

        top5 = g.nsmallest(5, 'r_finish')
        featured_this_year = g[g['Name'].isin(FEATURED_NAMES)]
        combined = pd.concat([top5, featured_this_year]).drop_duplicates(subset=['Name'])
        combined = combined.sort_values('r_finish')
        rows = combined[['Name', 'r_swim', 'r_bike', 'r_finish']].copy()
        rows['featured'] = rows['Name'].isin(FEATURED_NAMES)
        bump[str(int(y))] = rows.to_dict(orient='records')
    return bump


def build_heatmap_legacy(df):
    """Superseded by build_heat_detail (which adds gender-splitting and
    sample sizes), kept for reference since it's still in the payload."""
    df = df.copy()
    df['AgeGroup'] = df['Age'].apply(age_group)
    years = sorted(df['Year'].unique().tolist())
    heat = df.groupby(['AgeGroup', 'Year'])['FinishSec'].mean().reset_index()
    grid = []
    for ag in AGE_ORDER:
        row = []
        for y in years:
            v = heat[(heat.AgeGroup == ag) & (heat.Year == y)]['FinishSec']
            row.append(round(v.iloc[0], 0) if len(v) else None)
        grid.append({'group': ag, 'values': row})
    return {'age_order': AGE_ORDER, 'years': years, 'grid': grid}


def build_heat_detail(df):
    """The actual heatmap section: age-group x year, filterable by
    gender, with sample size attached to every cell so the UI can dim
    (and flag) cells built from fewer than 5 results."""
    df = df.copy()
    df['AgeGroup'] = df['Age'].apply(age_group)
    years = sorted(df['Year'].unique().tolist())

    def build_detail(sub):
        grp = sub.groupby(['AgeGroup', 'Year'])['FinishSec'].agg(['mean', 'count']).reset_index()
        detail = {}
        for y in years:
            detail[str(y)] = {}
            for ag in AGE_ORDER:
                row = grp[(grp.AgeGroup == ag) & (grp.Year == y)]
                if len(row):
                    detail[str(y)][ag] = {'avg': round(row['mean'].iloc[0], 1), 'n': int(row['count'].iloc[0])}
                else:
                    detail[str(y)][ag] = None
        return detail

    heat_detail = {
        'ALL': build_detail(df),
        'M': build_detail(df[df.Sex == 'M']),
        'F': build_detail(df[df.Sex == 'F']),
    }
    heat_meta = {'age_order': AGE_ORDER, 'years': years}
    return heat_detail, heat_meta


def build_age_pace_by_year(df):
    """Used by the featured-racer 'vs. age-group average' comparison
    (the tightest of the three lenses: controls for both the tide/course
    effect and for the racer's own age)."""
    df = df.copy()
    df['AgeGroup'] = df['Age'].apply(age_group)
    grp = df.groupby(['Year', 'AgeGroup'])[LEGS].mean().reset_index()
    grp['n'] = df.groupby(['Year', 'AgeGroup'])['Name'].count().values
    out = {}
    for _, row in grp.iterrows():
        y = str(int(row.Year))
        out.setdefault(y, {})[row.AgeGroup] = {
            'swim': round(row.SwimSec, 1), 't1': round(row.T1Sec, 1), 'bike': round(row.BikeSec, 1),
            't2': round(row.T2Sec, 1), 'run': round(row.RunSec, 1), 'n': int(row.n),
        }
    return out


def build_named_racers(df):
    """'Featured racers' section -- full result history for a specific
    list of names."""
    cols = ['Year', 'Age', 'OverallPlace', 'DivCode', 'DivPlace', 'DivTotal',
            'FinishSec', 'FinishTimeStr', 'SwimSec', 'T1Sec', 'BikeSec', 'T2Sec', 'RunSec']
    out = []
    for name in FEATURED_NAMES:
        g = df[df['Name'] == name].sort_values('Year')
        out.append({'name': name, 'races': g[cols].to_dict(orient='records')})
    return out


def build_galaxy(df):
    """'Every division, at a glance' force-simulated bubble view.
    Grouped by age-group x sex rather than the race's own division codes,
    since those codes weren't consistent across years for younger age
    brackets (M0013/M0014/M0017/M0019/M1419/M1519/M1824 all really
    describe overlapping flavors of 'under 20')."""
    df = df.copy()
    df['AgeGroup'] = df['Age'].apply(age_group)
    grp = df.groupby(['AgeGroup', 'Sex']).agg(
        n=('Name', 'count'), avg_finish=('FinishSec', 'mean'), avg_age=('Age', 'mean'),
    ).reset_index()
    galaxy = []
    for _, r in grp.iterrows():
        galaxy.append({
            'div': f'{r.Sex}{r.AgeGroup}', 'label': r.AgeGroup, 'n': int(r.n),
            'avg_finish': round(r.avg_finish, 1), 'avg_age': round(r.avg_age, 1), 'sex': r.Sex,
        })
    return galaxy


def main():
    df = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(df)} rows from {INPUT_PATH}")

    heat_detail, heat_meta = build_heat_detail(df)

    payload = {
        'yearly': build_yearly(df),
        'pace_by_year': build_pace_by_year(df),
        'overall_pace': build_overall_pace(df),
        'records_by_year': build_records_by_year(df),
        'top_fastest': build_top_fastest(df),
        'perfect_attendance': build_perfect_attendance(df),
        'age_scatter': build_age_scatter(df),
        'explorer': build_explorer(df),
        'meta': build_meta(df),
        'agegroup_stats': build_agegroup_stats(df),
        'regression': build_regression(df),
        'bump': build_bump(df),
        'heatmap': build_heatmap_legacy(df),
        'named_racers': build_named_racers(df),
        'age_trend': build_age_trend(df),
        'galaxy': build_galaxy(df),
        'age_pace_by_year': build_age_pace_by_year(df),
        'heat_detail': heat_detail,
        'heat_meta': heat_meta,
    }

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(payload, f, default=str)

    import os
    print(f"Saved {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH)/1024:.0f} KB)")
    print(f"Keys: {list(payload.keys())}")


if __name__ == '__main__':
    main()
