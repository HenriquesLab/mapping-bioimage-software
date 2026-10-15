"""Figure 4: exploratory research-vocabulary associations.

Coloured circles mark contrasts meeting a fold-change threshold and a pointwise
bootstrap criterion, without multiplicity adjustment; their size shows the
weighted share of 2021-2025 papers naming the software that mention the area.
Pairs without a clear difference are small grey dots. Shared papers can
contribute to several tools; keywords do not identify the task performed.
"""

from __future__ import annotations

import numpy as np

from . import style as fs
from . import domains as dm
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

TYPE_COL = "Computational methods"
MIN_FOLD = 1.5
DOT = "#d4d4d4"   # pairs without a clear difference
SIZE = lambda share: 12 + 3.2 * share   # noqa: E731  marker area (pt^2) from a percentage
# Columns grouped by topic: techniques and materials, organisms and development,
# cell biology, tissue and disease. Areas below the precision rule are dropped.
GROUPS = [["Electron microscopy", "Materials science"],
          ["Plant biology", "Microbiology and infection", "Development and organoids"],
          ["Organelles and cytoskeleton", "Single-cell and spatial omics"],
          ["Neuroscience", "Cancer", "Immunology", "Clinical and pathology",
           "Metabolic disease and liver", "Cardiovascular and renal"]]
SHORT = {"Microbiology and infection": "Microbiology, infection", "Development and organoids": "Development, organoids",
         "Organelles and cytoskeleton": "Organelles, cytoskeleton", "Clinical and pathology": "Clinical, pathology",
         "Metabolic disease and liver": "Metabolism, liver", "Materials science": "Materials", "Plant biology": "Plants",
         "Single-cell and spatial omics": "Spatial omics", "Cardiovascular and renal": "Cardiovascular, renal"}


def build_figure():
    fs.set_style()
    tools = fs.load("tools.csv").set_index("tool_id")
    e = fs.load("domain_enrichment.csv")
    # areas whose keywords marked research in the area in under half of the checked matches
    prec = fs.load("domain_precision_2025.csv").set_index("area")
    counts = fs.europepmc_yearly()
    last = counts[counts["year"] == 2025].set_index("tool_id")["count"]
    rows = sorted(e["tool_id"].unique(), key=lambda t: -float(last.get(t, 0)))
    cols, xs, x = [], [], -1.0
    for group in GROUPS:
        shown = [a for a in group if prec.loc[a, "shown"]]
        x += 0.35 if cols and shown else 0
        for a in shown:
            x += 1
            cols.append(a)
            xs.append(x)
    cols.append(TYPE_COL)
    xs.append(x + 1.6)
    e = e.set_index(["tool_id", "domain"])
    norm = TwoSlopeNorm(0, -2, 2)
    cmap = plt.get_cmap("BrBG")

    fig, ax = plt.subplots(figsize=(7.1, 4.9))
    for i, t in enumerate(rows):
        yi = len(rows) - 1 - i
        for x, c in zip(xs, cols):
            r = e.loc[(t, c)]
            if (r.lo > 1 or r.hi < 1) and (r.ratio >= MIN_FOLD or r.ratio <= 1 / MIN_FOLD):
                ax.scatter(x, yi, s=SIZE(r.share), color=cmap(norm(np.log2(np.clip(r.ratio, 0.25, 4)))), lw=0, zorder=3)
            else:
                ax.scatter(x, yi, s=6, color=DOT, lw=0, zorder=2)
    ax.set_xticks(xs, [SHORT.get(c, c) for c in cols], fontsize=6.6, rotation=40, ha="left", rotation_mode="anchor")
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)), [fs.tool_label(tools.loc[t, "name"]) for t in rows][::-1], fontsize=7)
    ax.set_xlim(xs[0] - 0.6, xs[-1] + 0.6)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)

    # legends: colour, then size
    colour_handles = [ax.scatter([], [], s=60, color=cmap(norm(v)), lw=0) for v in (2, 1, 0.6)] + \
                     [ax.scatter([], [], s=60, color=cmap(norm(-v)), lw=0) for v in (0.6, 1, 2)] + \
                     [ax.scatter([], [], s=6, color=DOT, lw=0)]
    leg = ax.legend(colour_handles, ["4× more often", "2× more often", "1.5× more often", "1.5× less often",
                                     "2× less often", "4× less often", "no clear\ndifference"],
                    title="Compared with\npapers mentioning\nother software", loc="upper left", bbox_to_anchor=(1.01, 1.0),
                    fontsize=6.5, title_fontsize=6.8, frameon=False)
    leg._legend_box.align = "left"
    ax.add_artist(leg)
    size_handles = [ax.scatter([], [], s=SIZE(v), color="#9a9a9a", lw=0) for v in (10, 25, 50)]
    leg = ax.legend(size_handles, ["10%", "25%", "50%"], title="Papers mentioning the\nsoftware that\nmention the area",
                    loc="upper left", bbox_to_anchor=(1.01, 0.44), fontsize=6.5, title_fontsize=6.8,
                    labelspacing=1.3, handletextpad=1.4, frameon=False)
    leg._legend_box.align = "left"
    fig.suptitle("Research areas over- and under-represented among papers mentioning each program (2021-2025)",
                 x=0.02, ha="left", fontsize=8.5)
    fig.subplots_adjust(left=0.14, right=0.80, bottom=0.03, top=0.79)
    return fig

def main(out_dir=None) -> None:
    fs.save(build_figure(), "Figure5__domains", out_dir=out_dir)


if __name__ == "__main__":
    main()
