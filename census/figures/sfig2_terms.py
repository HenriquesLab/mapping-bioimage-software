"""Supplementary Figure 2: over-represented words, shown with their prevalence.

For each tool, the eight words most over-represented in its randomly sampled
2021-2025 abstracts (weighted log-odds against all other dedicated tools,
restricted to words in at least 2% of its abstracts). Each row shows the share
of the tool's abstracts containing the word (filled) against the share among
all other tools (open), so the reader sees prevalence as well as rank.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import style as fs
from . import domains as dm
import matplotlib.pyplot as plt  # noqa: E402

TOOLS = ["imagej", "imaris", "qupath", "cellprofiler", "cellpose", "stardist", "napari", "arivis"]
DISPLAY_WORD = {"specie": "species", "inhibit": "inhibition"}


def build_figure(terms=None):
    fs.set_style()
    tools = fs.load("tools.csv").set_index("tool_id")
    d = dm.load_corpus() if terms is None else None
    fig, axes = plt.subplots(2, 4, figsize=(7.1, 4.4))
    for k, (ax, t) in enumerate(zip(axes.flat, TOOLS)):
        x = (dm.enriched_terms(d, t) if terms is None
             else terms.loc[terms["tool_id"] == t]).iloc[::-1]
        y = np.arange(len(x))
        colour = fs.licence_colour(tools.loc[t, "category"])
        ax.hlines(y, x["base_pct"], x["tool_pct"], color="#cccccc", lw=1.2)
        ax.scatter(x["base_pct"], y, s=16, facecolor="white", edgecolor="#777777", lw=0.8, zorder=3)
        ax.scatter(x["tool_pct"], y, s=18, color=colour, zorder=4)
        ax.set_yticks(y, [DISPLAY_WORD.get(word, word) for word in x["word"]], fontsize=6.4)
        ax.set_xlim(-1, max(31, float(x["tool_pct"].max()) * 1.1))
        ax.set_xticks(range(0, int(ax.get_xlim()[1]) + 1, 10))
        ax.tick_params(axis="x", labelsize=6)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e8edf1", lw=0.5)
        ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False)
        ax.set_title(fs.tool_label(tools.loc[t, "name"]), loc="left", fontsize=7.2, pad=2)
        fs.panel_label(ax, "abcdefgh"[k], x=-0.42, y=1.02)
    fig.supxlabel("Abstracts containing the word (%): package (filled) and all other packages (open)", fontsize=7)
    fig.tight_layout(h_pad=1.0, w_pad=0.8)
    return fig


TERMS_TABLE = Path(__file__).resolve().parents[2] / "notebooks/data/sfigure2_terms.csv"


def main(out_dir=None) -> None:
    terms = None
    # The article corpus is refetched locally (release/refetch_identifiers.py); a fresh clone uses the tracked term table.
    if not (fs.PROCESSED / "random_sample_2021_2025.csv.gz").exists():
        terms = pd.read_csv(TERMS_TABLE)
    fs.save(build_figure(terms), "SFigure2__terms", out_dir=out_dir)


if __name__ == "__main__":
    main()
