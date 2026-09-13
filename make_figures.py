"""Generate Fig. 2 and Fig. 3 for the Atheneum paper from your own measurements.

Usage:
    pip install matplotlib
    python make_figures.py

Reads comparison.csv and reader_study.csv from this folder and writes
fig2_comparison.png and fig3_reader_study.png at 300 dpi, sized for a
single IEEE column. Paste each into the dashed placeholder box in the docx.

Both CSVs ship with empty value columns. Fill them from your evaluation runs.
The script refuses to plot empty cells rather than inventing anything.
"""
import csv
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit("matplotlib is not installed. Run: pip install matplotlib")

COL_W, DPI = 3.4, 300           # IEEE single column is about 3.4 inches
GREYS = ["#b8b8b8", "#7a7a7a", "#2e2e2e"]


def load(path):
    with open(path, newline="", encoding="utf8") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].lstrip().startswith("#")]
    header, data = rows[0], rows[1:]
    missing = [r[0] for r in data if any(c.strip() == "" for c in r[1:])]
    if missing:
        sys.exit("%s still has empty values for: %s\n"
                 "Fill them in from your evaluation runs first."
                 % (path, ", ".join(missing)))
    return header, data


def grouped_bars(path, out, title, ylabel, ymax):
    header, data = load(path)
    labels = [r[0].replace(" ", "\n", 1) if len(r[0]) > 12 else r[0] for r in data]
    systems = header[1:]
    fig, ax = plt.subplots(figsize=(COL_W, COL_W * 0.72))
    n = len(systems)
    width = 0.8 / n
    xs = range(len(labels))
    for i, sysname in enumerate(systems):
        vals = [float(r[i + 1]) for r in data]
        ax.bar([x + i * width - 0.4 + width / 2 for x in xs], vals, width,
               label=sysname, color=GREYS[i % len(GREYS)],
               edgecolor="black", linewidth=0.5)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_ylim(0, ymax)
    ax.set_title(title, fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.legend(fontsize=6.5, frameon=False, loc="upper left", ncol=n)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linewidth=0.4, alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout(pad=0.3)
    fig.savefig(out, dpi=DPI)
    print("wrote", out)


grouped_bars("comparison.csv", "fig2_comparison.png",
             "Baselines vs. Atheneum", "Score (%)", 100)
grouped_bars("reader_study.csv", "fig3_reader_study.png",
             "Mean reader ratings", "Rating (1-5)", 5)
