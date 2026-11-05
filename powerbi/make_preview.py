"""Draw the four dashboard charts with matplotlib from the same files Power BI reads, so the Power BI visuals can be checked against them.
Output: powerbi/preview/chart_1..4_*.png, dashboard_preview.png, numbers.txt.     Run: python powerbi/make_preview.py"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "powerbi", "preview")
os.makedirs(OUT, exist_ok=True)
COL = {"baseline-flat": "#7a7a7a", "proposed": "#2f6db5", "proposed+improved": "#d9822b"}
REG = ["#2f6db5", "#d9822b", "#3a9a5b", "#b04a8f", "#8c6d1f", "#4aa3a8"]

t = pd.read_csv(os.path.join(ROOT, "data", "telemetry_120k.csv"), parse_dates=["timestamp"])
cap = pd.read_csv(os.path.join(ROOT, "results", "m12_capstone_summary.csv"))
t["hour_start"] = t["timestamp"].dt.floor("h")

fig, ax = plt.subplots(2, 2, figsize=(15, 9))


def line_regions(a):
    h = t.groupby(["hour_start", "region"])["latency_ms"].mean().unstack()
    h = h.resample("D").mean() if len(h) > 400 else h        # daily means keep the chart readable over ~17 days
    for i, r in enumerate(h.columns):
        a.plot(h.index, h[r], label=r, color=REG[i % len(REG)], lw=1.4)
    a.set_title("1  Latency by region over time (daily mean, ms)")
    a.set_ylabel("avg latency (ms)")
    a.legend(ncol=3, fontsize=8)
    import matplotlib.dates as mdates
    a.xaxis.set_major_locator(mdates.DayLocator(interval=4))
    a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))


def bar_sites(a):
    s = t.groupby("site_id")["is_anomaly"].sum().sort_values()
    a.barh(s.index, s.values, color="#2f6db5")
    a.set_title("2  Anomalous readings by site")
    a.set_xlabel("anomaly rows")
    a.tick_params(axis="y", labelsize=7)


def grouped(a, sweep, ycol, title, ylabel, log=False):
    d = cap[cap.sweep == sweep]
    levels = list(d.sort_values("level_order")["level"].drop_duplicates())
    systems = [s for s in COL if s in set(d.system)]
    w = 0.8 / len(systems)
    for j, s in enumerate(systems):
        ys = [d[(d.level == l) & (d.system == s)][ycol].mean() for l in levels]
        a.bar([i + j * w for i in range(len(levels))], ys, w, label=s, color=COL[s])
    a.set_xticks([i + w * (len(systems) - 1) / 2 for i in range(len(levels))])
    a.set_xticklabels([str(l) for l in levels])
    a.set_title(title)
    a.set_ylabel(ylabel)
    if log:
        a.set_yscale("log")
    a.legend(fontsize=8)


def line_levels(a, sweep, ycol, title, ylabel):
    d = cap[cap.sweep == sweep]
    levels = list(d.sort_values("level_order")["level"].drop_duplicates())
    for s in COL:
        if s in set(d.system):
            ys = [d[(d.level == l) & (d.system == s)][ycol].mean() for l in levels]
            style = dict(marker="o", ms=9, mfc="none", lw=1.2, ls="--") if s == "proposed" else dict(marker="o", ms=5, lw=1.8)   # hollow + dashed so that identical lines stay visible
            a.plot(range(len(levels)), ys, label=s, color=COL[s], **style)
    a.set_xticks(range(len(levels)))
    a.set_xticklabels([str(l) for l in levels])
    a.set_title(title)
    a.set_ylabel(ylabel)
    a.legend(fontsize=8)


charts = [
    ("chart_1_latency_by_region", lambda a: line_regions(a)),
    ("chart_2_anomalies_by_site", lambda a: bar_sites(a)),
    ("chart_3_bandwidth_completion", lambda a: (grouped(a, "bandwidth", "complete_s_mean", "3  Time to deliver 120,000 rows vs link bandwidth (Mbit/s)", "seconds (log)", log=True), a.set_xlabel("edge->core link bandwidth"))),
    ("chart_4_availability_vs_crashes", lambda a: (line_levels(a, "failure_rate", "ingest_availability_pct_mean", "4  Ingest availability vs crashes per minute", "% of 100 ms write probes accepted"), a.set_xlabel("core/collector crashes per minute"))),
]
for k, (name, fn) in enumerate(charts):
    fn(ax[k // 2][k % 2])
    f1, a1 = plt.subplots(figsize=(7.5, 4.5))
    fn(a1)
    f1.tight_layout()
    f1.savefig(os.path.join(OUT, name + ".png"), dpi=130)
    plt.close(f1)
fig.suptitle("Distributed Network Monitoring - telemetry (120,000 rows) and Milestone 12 capstone results", fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "dashboard_preview.png"), dpi=130)
with open(os.path.join(OUT, "numbers.txt"), "w") as f:
    f.write(f"Rows = {len(t):,}\nSites Reporting = {t.site_id.nunique()}\nAnomaly Rows = {int(t.is_anomaly.sum()):,}\n"
            f"Anomaly Rate % = {100 * t.is_anomaly.mean():.3f}\nAvg Latency (ms) = {t.latency_ms.mean():.3f}\nP95 Latency (ms) = {t.latency_ms.quantile(.95):.3f}\n"
            f"Avg CPU % = {t.cpu_pct.mean():.3f}\nAvg Jitter (ms) = {t.jitter_ms.mean():.3f}\n")
print(open(os.path.join(OUT, "numbers.txt")).read())
