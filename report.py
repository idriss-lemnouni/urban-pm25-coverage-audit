"""Export county coverage, monthly coverage and paired event sensitivity."""
import calendar
import csv
from html import escape
from pathlib import Path
import sqlite3

ANNUAL = """
WITH observations AS (
    SELECT region, count(*) AS observed_days, avg(county_site_mean) AS observed_mean
    FROM county_days GROUP BY region
), sites AS (
    SELECT region, count(DISTINCT site) AS reporting_sites
    FROM site_days GROUP BY region
)
SELECT r.region, r.state, r.county, coalesce(o.observed_days, 0),
       coalesce(s.reporting_sites, 0), round(o.observed_mean, 3)
FROM regions r
LEFT JOIN observations o USING (region)
LEFT JOIN sites s USING (region)
ORDER BY r.region
"""
MONTHLY = """
SELECT region, cast(substr(day, 6, 2) AS INTEGER) AS month, count(*)
FROM county_days GROUP BY region, month
"""
PAIRS = """
SELECT region, count(*) AS matched_instrument_days,
       sum(exclusion_delta <> 0) AS changed,
       round(avg(exclusion_delta), 3) AS mean_delta,
       round(avg(abs(exclusion_delta)), 3) AS mean_absolute_delta
FROM monitor_days WHERE exclusion_delta IS NOT NULL
GROUP BY region ORDER BY region
"""


def export(path: Path, columns: tuple, records) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(columns)
        writer.writerows(records)


def write_reports(db: sqlite3.Connection, stage: Path, quality: dict) -> None:
    year = quality["year"]
    elapsed_days = quality["days"]
    annual = [
        (region, state, county, days, elapsed_days, round(days / elapsed_days, 6), sites, mean)
        for region, state, county, days, sites, mean in db.execute(ANNUAL)
    ]
    export(stage / "county_coverage.csv", (
        "aqs_region", "state", "county", "observed_days", "calendar_days",
        "coverage", "reporting_sites", "mean_observed_ug_m3",
    ), annual)
    monthly = {(region, month): days for region, month, days in db.execute(MONTHLY)}
    export(stage / "monthly_coverage.csv", (
        "aqs_region", "month", "observed_days", "calendar_days"
    ), (
        (row[0], f"{year}-{month:02d}", monthly.get((row[0], month), 0), calendar.monthrange(year, month)[1])
        for row in annual for month in range(1, 13)
    ))
    pairs = list(db.execute(PAIRS))
    export(stage / "event_sensitivity.csv", (
        "aqs_region", "matched_instrument_days", "changed", "mean_delta_ug_m3", "mean_absolute_delta_ug_m3"
    ), pairs)
    quality["regions"] = len(annual)
    quality["regions_with_daily_coverage"] = sum(row[3] > 0 for row in annual)
    quality["fully_observed_regions"] = sum(row[3] == elapsed_days for row in annual)
    quality["regions_below_half_coverage"] = sum(row[3] * 2 < elapsed_days for row in annual)
    quality["matched_event_pairs"] = sum(row[1] for row in pairs)
    quality["changed_event_pairs"] = sum(row[2] for row in pairs)
    quality["weighted_mean_absolute_event_delta"] = db.execute(
        "SELECT round(avg(abs(exclusion_delta)), 3) FROM monitor_days"
    ).fetchone()[0]
    render(stage / "coverage.html", annual, quality)


def render(path: Path, rows: list[tuple], quality: dict) -> None:
    content = []
    for region, state, county, days, _, coverage, sites, mean in sorted(
        rows, key=lambda row: (row[3], row[1], row[2])
    ):
        label = escape(f"{county}, {state}")
        mean_text = "—" if mean is None else f"{mean:.3f}"
        content.append(
            f'<tr><th scope="row">{label}</th><td>{region}</td><td>{days}</td>'
            f'<td><meter min="0" max="1" value="{coverage}">{coverage:.1%}</meter> {coverage:.1%}</td>'
            f'<td>{sites}</td><td>{mean_text}</td></tr>'
        )
    html = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PM2.5 monitoring coverage | {quality['year']}</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:66rem;padding:2rem 1rem;margin:auto;color:#163135;background:#f7faf9}}
h1{{letter-spacing:-.04em}} a{{color:#075766}} input{{font:inherit;padding:.4rem;margin-bottom:1rem}}
table{{border-collapse:collapse;width:100%;background:white}} td,th{{border-bottom:1px solid #d8e4e3;padding:.55rem;text-align:left}}
thead{{background:#e1efeb}} meter{{width:5rem;accent-color:#00786e}} .scroll{{overflow:auto}}
</style>
<h1>PM2.5 monitoring coverage · {quality['year']}</h1>
<p>{quality['regions_with_daily_coverage']} of {quality['regions']} reported AQS regions have an eligible daily PM2.5 observation.
{quality['regions_below_half_coverage']} regions have observations on fewer than half of calendar days.</p>
<p>Coverage means a reported observation at one or more sites on a calendar day. The observed mean weights sites equally within a day and observed days equally within a region.</p>
<p><a href="county_coverage.csv">County CSV</a> · <a href="monthly_coverage.csv">Monthly CSV</a> · <a href="event_sensitivity.csv">Event sensitivity CSV</a></p>
<label for="filter">Filter by state, county or AQS code</label><br><input id="filter" type="search">
<div class="scroll"><table><thead><tr><th>County</th><th>AQS code</th><th>Observed days</th>
<th>Calendar coverage</th><th>Sites</th><th>Observed mean (µg/m³)</th></tr></thead><tbody>
{''.join(content)}
</tbody></table></div>
<script>
const filter = document.getElementById('filter');
const rows = document.querySelectorAll('tbody tr');
filter.addEventListener('input', () => {{
  const query = filter.value.toLowerCase().trim();
  for (const row of rows) row.hidden = !row.textContent.toLowerCase().includes(query);
}});
</script></html>
"""
    path.write_text(html, encoding="utf-8")
