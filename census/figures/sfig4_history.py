"""Supplementary Figure 4: package mentions across the 1995-2025 corpus.

Each package appears in its own panel, coloured by registry category. The top
panel shows the yearly Europe PMC microscopy-corpus size; the shaded early years
mark the period with sparse, archive-dominated coverage.
"""

from __future__ import annotations

import math

import pandas as pd
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt  # noqa: E402

from . import style as fs

START_YEAR = 1995
EARLY_CORPUS_END = 2007
MAX_COLUMNS = 5
TICKS = [1995, 2005, 2015, 2025]
TICK_LABELS = ["'95", "'05", "'15", "'25"]
EARLY_SHADE = "#F3E7D9"


def _fmt(v: float) -> str:
    return f"{v:.2g}%" if v < 1 else fs.pct(v)


def _included(value) -> bool:
    return str(value).strip().lower() == "true"


def _load_inputs() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    history = pd.read_csv(fs.PROCESSED / "historical_mentions_yearly.csv")
    counts = pd.concat([fs.europepmc_yearly(), history], ignore_index=True)
    historical_corpus = pd.read_csv(fs.PROCESSED / "historical_corpus_yearly.csv")
    corpus = pd.concat([
        historical_corpus.set_index("year")["microscopy_papers"],
        fs.corpus(),
    ]).sort_index()
    tools = fs.load("tools.csv").set_index("tool_id")
    return counts, corpus, tools


def build_figure(
    counts: pd.DataFrame | None = None,
    corpus: pd.Series | None = None,
    tools: pd.DataFrame | None = None,
):
    """Build the full-period figure; optional inputs keep the renderer testable offline."""
    fs.set_style()
    if counts is None or corpus is None or tools is None:
        loaded_counts, loaded_corpus, loaded_tools = _load_inputs()
        counts = loaded_counts if counts is None else counts
        corpus = loaded_corpus if corpus is None else corpus
        tools = loaded_tools if tools is None else tools

    counts = counts.copy()
    counts["year"] = counts["year"].astype(int)
    counts = counts.groupby(["tool_id", "year"], as_index=False)["count"].sum()
    corpus = corpus.copy()
    corpus.index = corpus.index.astype(int)
    corpus = corpus.sort_index()
    years = corpus.index.tolist()
    if not years or years[0] != START_YEAR or years[-1] != 2025:
        raise ValueError("The historical figure needs corpus data from 1995 through 2025")
    if corpus.isna().any() or (corpus <= 0).any():
        raise ValueError("Every plotted year needs a positive microscopy-corpus denominator")

    totals = counts.groupby("tool_id")["count"].sum()
    by_year = counts.set_index(["tool_id", "year"])["count"]
    registry_order = {tool_id: i for i, tool_id in enumerate(tools.index)}
    order = [tool_id for tool_id in tools.index if totals.get(tool_id, 0) > 0]
    order.sort(key=lambda tool_id: (
        -float(by_year.get((tool_id, years[-1]), 0)),
        -float(totals.get(tool_id, 0)),
        registry_order[tool_id],
    ))
    if not order:
        raise ValueError("No registry packages have mentions in the plotted period")

    ncols = min(MAX_COLUMNS, len(order))
    nrows = math.ceil(len(order) / ncols)
    fig = plt.figure(figsize=(7.1, 1.35 + 1.12 * nrows))
    grid = fig.add_gridspec(
        nrows + 1,
        ncols,
        height_ratios=[0.9] + [1.0] * nrows,
        hspace=0.95,
        wspace=0.55,
    )
    corpus_ax = fig.add_subplot(grid[0, :])
    corpus_ax.axvspan(
        START_YEAR, EARLY_CORPUS_END + 0.5,
        color=EARLY_SHADE, alpha=0.75, lw=0, zorder=0,
    )
    corpus_ax.plot(years, corpus.values, color=fs.INK, lw=1.25, zorder=2)
    corpus_ax.set_yscale("log")
    corpus_ax.set_xlim(START_YEAR, years[-1])
    positive = corpus[corpus > 0]
    corpus_ax.set_ylim(max(1, float(positive.min()) * 0.8), float(positive.max()) * 1.2)
    ticks = [value for value in (5_000, 10_000, 20_000, 50_000, 100_000, 200_000, 500_000)
             if corpus_ax.get_ylim()[0] <= value <= corpus_ax.get_ylim()[1]]
    if ticks:
        corpus_ax.set_yticks(ticks, [f"{value / 1000:g}k" for value in ticks])
    corpus_ax.set_ylabel("Microscopy papers (log scale)", fontsize=6.5)
    corpus_ax.set_title("Europe PMC microscopy corpus", loc="left", fontsize=7, pad=3)
    corpus_ax.set_xticks(TICKS, TICK_LABELS)
    corpus_ax.tick_params(labelbottom=False, labelsize=5.8, length=1.5)
    corpus_ax.grid(axis="y", color=fs.GRID, lw=0.5, zorder=0.5)
    corpus_ax.text(
        START_YEAR + 0.4, 0.92, "early corpus, archive-limited",
        transform=corpus_ax.get_xaxis_transform(), ha="left", va="top",
        fontsize=5.6, color=fs.MUTED,
    )

    top_packages = set(order[:10])
    package_axes = []
    for i, tool_id in enumerate(order):
        ax = fig.add_subplot(grid[1 + i // ncols, i % ncols])
        package_axes.append(ax)
        ax.axvspan(
            START_YEAR, EARLY_CORPUS_END + 0.5,
            color=EARLY_SHADE, alpha=0.75, lw=0, zorder=0,
        )
        count_series = by_year.loc[tool_id] if tool_id in by_year.index.get_level_values(0) else pd.Series(dtype=float)
        count_series = count_series.reindex(years, fill_value=0)
        share = 100.0 * count_series.to_numpy(dtype=float) / corpus.to_numpy(dtype=float)
        category = tools.loc[tool_id, "category"]
        colour = fs.CATEGORY_COLOR.get(category, fs.MUTED)
        important = tool_id in top_packages
        ax.plot(years, share, color=colour, lw=1.1 if important else 0.9,
                alpha=1.0 if important else 0.78, zorder=2)
        name = fs.tool_label(tools.loc[tool_id, "name"])
        if not _included(tools.loc[tool_id, "in_aggregate"]):
            name += "*"
        ax.set_title(
            name, loc="left", fontsize=6.5 if important else 5.8,
            color=fs.INK if important else fs.MUTED,
            fontweight="bold" if important else "normal", pad=2,
        )
        peak = float(share.max())
        ax.set_ylim(0, peak * 1.25 if peak > 0 else 1)
        ax.set_yticks([0, peak] if peak > 0 else [0], ["0", _fmt(peak)] if peak > 0 else ["0"])
        ax.set_xlim(START_YEAR, years[-1])
        ax.set_xticks(TICKS, TICK_LABELS)
        ax.tick_params(labelsize=5.4, length=1.3, pad=1.5)
        ax.grid(axis="y", color=fs.GRID, lw=0.45, zorder=0.5)

    present_categories = list(dict.fromkeys(tools.loc[tool_id, "category"] for tool_id in order))
    short_labels = {"figure-preparation": "figure preparation"}
    handles = [
        Line2D([0], [0], color=fs.CATEGORY_COLOR.get(category, fs.MUTED), lw=1.5,
               label=short_labels.get(category, fs.CATEGORY_LABEL.get(category, category)))
        for category in present_categories
    ]
    fig.legend(handles=handles, loc="lower center", ncol=min(4, len(handles)),
               frameon=False, fontsize=5.7, columnspacing=1.1, handlelength=1.3,
               bbox_to_anchor=(0.52, 0.005))
    fig.supylabel("Package mentions as share of corpus (%)", x=0.01, fontsize=6.5)
    fig.suptitle(
        "Package mentions as a share of full-text microscopy papers, 1995–2025",
        x=0.02, y=0.995, ha="left", fontsize=8.5, fontweight="bold",
    )
    fig.subplots_adjust(left=0.07, right=0.995, top=0.965, bottom=0.055)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "SFigure4__history", out_dir=out_dir)


if __name__ == "__main__":
    main()
