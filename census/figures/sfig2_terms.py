"""Supplementary Figure 2: over-represented words, shown with their prevalence.

For each tool, the eight words most over-represented in its randomly sampled
2021-2025 abstracts (weighted log-odds against all other dedicated tools,
restricted to words in at least 2% of its abstracts). Each row shows the share
of the tool's abstracts containing the word (filled) against the share among
all other tools (open), so the reader sees prevalence as well as rank.
"""

from __future__ import annotations

import numpy as np

from . import style as fs
from . import domains as dm
import matplotlib.pyplot as plt  # noqa: E402

TOOLS = ["imagej", "imaris", "qupath", "cellprofiler", "cellpose", "stardist", "napari", "arivis"]


def build_figure():
    fs.set_style()
    tools = fs.load("tools.csv").set_index("tool_id")
    d = dm.load_corpus()
    fig, axes = plt.subplots(2, 4, figsize=(7.1, 4.4))
    for k, (ax, t) in enumerate(zip(axes.flat, TOOLS)):
        x = dm.enriched_terms(d, t).iloc[::-1]
        y = np.arange(len(x))
        colour = fs.licence_colour(tools.loc[t, "category"])
        ax.hlines(y, x["base_pct"], x["tool_pct"], color="#cccccc", lw=1.2)
        ax.scatter(x["base_pct"], y, s=16, facecolor="white", edgecolor="#777777", lw=0.8, zorder=3)
        ax.scatter(x["tool_pct"], y, s=18, color=colour, zorder=4)
        ax.set_yticks(y, x["word"], fontsize=6.4)
        ax.set_xlim(0, max(30, float(x["tool_pct"].max()) * 1.1))
        ax.tick_params(axis="x", labelsize=6)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e8edf1", lw=0.5)
        ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False)
        ax.set_title(fs.tool_label(tools.loc[t, "name"]), loc="left", fontsize=7.2, pad=2)
        fs.panel_label(ax, "abcdefgh"[k], x=-0.42, y=1.02)
    fig.supxlabel("Abstracts containing the word (%): package (filled) and all other packages (open)", fontsize=7)
    fig.suptitle("Words most over-represented in each package's papers, with how often they appear", x=0.02, ha="left", fontsize=8.5)
    fig.tight_layout(h_pad=1.0, w_pad=0.8)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "SFigure2__terms", out_dir=out_dir)


if __name__ == "__main__":
    main()
