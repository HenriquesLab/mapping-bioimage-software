"""Supplementary Figure 3: three adoption signals, same tools, same order.

Each source keeps its own units and its own axis. Placing them side by side on a
shared row order shows how far a claim of wide use depends on which signal is
quoted.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator  # noqa: E402

# Every registry tool with a public GitHub repository (Icy, KNIME and the
# commercial suites have none, so two of the three signals would be empty).
TOOLS = ["imagej", "qupath", "cellprofiler", "ilastik", "napari",
         "cellpose", "stardist", "zerocostdl4mic", "deepimagej"]
METRICS = [
    ("Papers mentioning\nthe package, 2010-2025", "Papers", "#0072B2"),
    ("GitHub stars\n(developer interest)", "Stars", "#E69F00"),
    ("Python package downloads,\n30 days", "Downloads", "#009E73"),
]


def build_figure():
    fs.set_style()
    lit = fs.europepmc_yearly()
    snap = fs.load("adoption_snapshot.csv").set_index("tool_id")
    names = fs.load("tools.csv").set_index("tool_id")["name"].to_dict()

    signals = pd.DataFrame(index=TOOLS)
    signals["lit"] = lit.groupby("tool_id")["count"].sum().reindex(TOOLS)
    signals["stars"] = snap["github_stars"].reindex(TOOLS)
    signals["pypi"] = snap["pypi_downloads_30d"].reindex(TOOLS)

    y = np.arange(len(TOOLS))[::-1]
    fig, axes = plt.subplots(1, 4, figsize=(7.1, 2.7), sharey=True,
                             gridspec_kw={"width_ratios": [0.62, 1, 1, 1], "wspace": 0.12})
    ax_name, *metric_axes = axes

    ax_name.set_xlim(0, 1)
    for yi, tool in zip(y, TOOLS):
        ax_name.text(1.0, yi, fs.tool_label(names.get(tool, tool)), ha="right", va="center", fontsize=7.5)
    ax_name.axis("off")

    for ax, col, (title, xlabel, colour), letter in zip(
            metric_axes, ["lit", "stars", "pypi"], METRICS, "abc"):
        values = pd.to_numeric(signals[col], errors="coerce")
        valid = values > 0
        ax.scatter(values[valid], y[valid.to_numpy()], s=28, color=colour, zorder=3)
        for yi, tool, v in zip(y, TOOLS, values):
            if v > 0:
                lab = f"{int(v):,}" + (" (pyimagej)" if col == "pypi" and tool == "imagej" else "")
                ax.text(v * 1.6, yi, lab, fontsize=5.8, color="#555555", ha="left", va="center")
            else:
                ax.text(0.5, yi, "no package", transform=ax.get_yaxis_transform(),
                        fontsize=6, color="#999999", ha="center", va="center")
        ax.set_xscale("log")
        ax.set_title(title, loc="left", fontsize=8)
        ax.set_xlabel(xlabel + " (log scale)", fontsize=7.5)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.grid(axis="x", color="#e3e9ee", lw=0.5)
        ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", labelsize=6.5)
        if valid.any():
            ax.set_xlim(values[valid].min() / 3, values[valid].max() * 60)
            fs.sparse_log_ticks(ax, values[valid].tolist(), n=2)
        fs.panel_label(ax, letter, x=-0.08, y=1.16)
    metric_axes[0].set_ylim(y.min() - 0.7, y.max() + 0.9)

    fig.suptitle("Papers, GitHub stars and downloads rank the same packages differently", x=0.02, ha="left", fontsize=8.5, y=1.12)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            'ignore', category=UserWarning,
            message='This figure includes Axes that are not compatible with tight_layout, so results might be incorrect[.]')
        fig.tight_layout()
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "SFigure3__triangulation", out_dir=out_dir)


if __name__ == "__main__":
    main()
