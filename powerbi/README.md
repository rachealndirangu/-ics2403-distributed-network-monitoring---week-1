# Power BI dashboard (lecturer requirement: a Power BI file with 2-4 charts)

**Honest status.** A `.pbix` is a binary format that only Power BI Desktop (Windows) can write, and this repository was
built on a Linux cloud machine, so **the `.pbix` itself is not in this repo — you create it in about 15 minutes with the
recipe below**. Everything it needs is here and tested: the 120,000-row dataset, the Milestone 12 result table, the
Power Query code, the DAX measures, and `preview/` PNGs showing exactly what each of the four charts shows (drawn with
matplotlib from the same files, so you can check your Power BI visuals against them).

## Data sources
| Table | File | Rows | Made by |
|---|---|---|---|
| `telemetry` | `data/telemetry_120k.csv` | 120,000 | `data/generate_dataset.py` (seed 2403) |
| `capstone`  | `results/m12_capstone_summary.csv` | one row per sweep x level x system | `python -m system.experiments.m12_analyze` |

## Steps
1. Power BI Desktop > **Transform data > Manage parameters > New**: name `DataFolder`, type Text, value = the repo folder
   path **with a trailing backslash**, e.g. `C:\Users\you\ics2403\`.
2. **New Source > Blank Query > Advanced Editor**: paste *Query 1* from `queries.pq`, name it `telemetry`.
   Repeat with *Query 2*, name it `capstone`. **Close & Apply**.
3. **Modeling > New measure**: paste the measures from `measures.dax` (the telemetry ones on `telemetry`, the others on `capstone`).
4. Add the four visuals (one page, 2x2 grid). Page title: *Distributed Network Monitoring - telemetry and capstone results*.

| # | Visual | Fields | Why it is there |
|---|---|---|---|
| 1 | **Line chart** "Latency by region over time" | X `telemetry[hour_start]`, Y `[Avg Latency (ms)]`, Legend `telemetry[region]` | Shows the diurnal load cycle and the regional incidents the monitoring system must detect |
| 2 | **Bar chart** "Anomalies by site" | Y `telemetry[site_id]`, X `[Anomaly Rows]`, tooltip `[Anomaly Rate %]` | Which sites need attention (labelled ground truth) |
| 3 | **Clustered column** "Time to deliver 120,000 rows vs link bandwidth" | X `capstone[level]`, Y `[Completion Time (s)]`, Legend `capstone[system]`; visual filter `sweep = bandwidth`; sort X by `capstone[level_order]`; log axis | Headline result of the capstone: where the proposed improvement wins and where it does not |
| 4 | **Line chart** "Ingest availability vs crash rate" | X `capstone[level]`, Y `[Ingest Availability %]`, Legend `capstone[system]`; visual filter `sweep = failure_rate`; sort X by `level_order` | Reliability result: flat collector vs replicated tiers |

5. Add two slicers if you have room (`telemetry[region]`, `telemetry[site_type]`) - they only affect visuals 1-2.
6. Save as `powerbi/ics2403_monitoring.pbix`, commit it, and submit it with the report.

## Checking your result
Compare each visual with `powerbi/preview/chart_N_*.png`. Totals to check on the telemetry page:
`[Rows]` = 120,000, `[Sites Reporting]` = 24, `[Anomaly Rows]` and `[Anomaly Rate %]` as printed in `powerbi/preview/numbers.txt`.
