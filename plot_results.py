"""Render publication figures from verified run artifacts."""
from collections import defaultdict
from pathlib import Path
import argparse
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

INK = "#172b3b"
MUTED = "#526575"
TEAL = "#007e78"
BLUE = "#4069ba"
ORANGE = "#b9502d"
SOFT = "#d5e1e7"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
    "axes.labelcolor": INK, "axes.titlecolor": INK, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": SOFT, "axes.axisbelow": True, "grid.color": SOFT,
    "grid.linewidth": 0.7, "legend.frameon": False,
})


def save(fig, out, name, title, note):
    fig.suptitle(title, x=0.055, y=0.96, ha="left", fontsize=21, fontweight="bold")
    fig.text(0.055, 0.035, note, ha="left", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0.025, .085, .995, .87), pad=1.5)
    fig.savefig(out / (name + ".png"), dpi=180, facecolor="white")
    plt.close(fig)

def render(run, out):
    def rows(name):
        with (run / name).open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))

    coverage = [int(r["observed_days"]) / int(r["calendar_days"]) for r in rows("county_coverage.csv")]
    bands = [sum(x < .5 for x in coverage), sum(.5 <= x < .75 for x in coverage),
             sum(.75 <= x < 1 for x in coverage), coverage.count(1.0)]
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    bars = ax.bar(["Below 50%", "50% to <75%", "75% to <100%", "Every day"], bands,
                  color=[ORANGE, "#deac76", BLUE, TEAL], width=.64)
    ax.bar_label(bars, padding=4, fontweight="bold")
    ax.set(ylabel="AQS regions", xlabel="Share of calendar days with an eligible observation",
           ylim=(0, max(bands) * 1.18))
    ax.grid(axis="y")
    save(fig, out, "annual-coverage", "Where daily PM₂.₅ observations were available",
         f"EPA AirData 2023 · {len(coverage):,} reporting AQS regions · calendar coverage, independent of sampling schedules")

    by_month = defaultdict(list)
    for row in rows("monthly_coverage.csv"):
        by_month[row["month"]].append(int(row["observed_days"]) / int(row["calendar_days"]))
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    months = sorted(by_month)
    boxes = ax.boxplot([by_month[m] for m in months], patch_artist=True, showfliers=False,
                        tick_labels=[m[-2:] for m in months], widths=.52,
                        medianprops={"color": INK, "linewidth": 1.8})
    for box in boxes["boxes"]:
        box.set(facecolor="#a8d9d3", edgecolor=TEAL)
    ax.set(xlabel="Month of 2023", ylabel="Coverage within an AQS region", ylim=(-.04, 1.06))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(axis="y")
    save(fig, out, "monthly-coverage", "Monthly coverage varied across reporting regions",
         "Boxes show the interquartile range and median across regions · whiskers use 1.5× IQR · outlier markers omitted")

    eligible = sorted(rows("event_sensitivity.csv"), key=lambda r: abs(float(r["mean_delta_ug_m3"])))
    top = eligible[-10:]
    delta = [float(r["mean_delta_ug_m3"]) for r in top]
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    handles = ax.barh([r["aqs_region"] + "   ·   n=" + r["matched_instrument_days"] for r in top],
                      delta, color=[ORANGE if v < 0 else TEAL for v in delta])
    ax.bar_label(handles, fmt="%+.1f", padding=4, fontsize=9)
    ax.axvline(0, color=INK, linewidth=.8)
    ax.set(xlabel="Mean paired difference, excluded minus included (µg/m³)", ylabel="AQS region code")
    ax.margins(x=.22)
    ax.grid(axis="x")
    save(fig, out, "event-sensitivity", "The largest regional effects of event exclusions",
         "Top ten by absolute mean difference · n = same-instrument matched summaries · effect conditional on available pairs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("runs/2023"))
    parser.add_argument("--out", type=Path, default=Path("figures/results"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    render(args.run, args.out)
