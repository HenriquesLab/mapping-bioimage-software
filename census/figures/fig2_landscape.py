"""Figure 2: the package landscape, ranked.

Row per registry package in one shared order, following the layout bibliometrics
papers use: the counts printed as a column, then each metric on its own axis.
The right column gives each package's growth since 2020, the first year in which
the deep-learning methods and napari appear, so the packages driving the change
are visible next to the packages carrying the volume. Each fold change is
printed with its 2020 count, because a fold change from few papers is fragile.
"""

from __future__ import annotations

import warnings

import numpy as np

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator  # noqa: E402

FIRST, LAST = 2010, 2025
GROWTH_FROM = 2020
FRAGILE = 20   # fold changes from fewer 2020 papers are drawn open and grey


def build_figure():
    fs.set_style()
    tools = fs.load("tools.csv").set_index("tool_id")
    counts = fs.europepmc_yearly()
    share = fs.share_of_total("analysis").set_index(["tool_id", "year"])["share"]

    ids = [t for t in tools.index if t in set(counts["tool_id"]) and t != "nihimage"]
    by_year = counts.set_index(["tool_id", "year"])["count"]
    rows = []
    for t in ids:
        last = float(by_year.get((t, LAST), 0))
        base = float(by_year.get((t, GROWTH_FROM), 0))
        rows.append({
            "tool_id": t,
            "name": tools.loc[t, "name"],
            "category": tools.loc[t, "category"],
            "last": last,
            "base": base,
            "growth": (last / base) if base > 0 else np.nan,
            "share_first": float(share.get((t, FIRST), np.nan)),
            "share_last": float(share.get((t, LAST), np.nan)),
        })
    # Dedicated packages ranked by volume; MATLAB and Jupyter notebooks sit
    # below a rule as references outside every aggregate.
    in_agg = set(fs.aggregate_tools())
    rows.sort(key=lambda r: (r["tool_id"] not in in_agg, -r["last"]))
    y = np.arange(len(rows))[::-1].astype(float)
    n_ref = sum(r["tool_id"] not in in_agg for r in rows)
    if n_ref:
        y[-n_ref:] -= 0.6

    fig, axes = plt.subplots(
        1, 3, figsize=(7.1, 1.35 + 0.108 * len(rows)), sharey=True,
        gridspec_kw={"width_ratios": [0.85, 1.5, 1.5], "wspace": 0.08})
    ax_n, ax_count, ax_share = axes

    colours = [fs.licence_colour(r["category"]) if r["tool_id"] in in_agg else "#c7c7c7" for r in rows]
    # The deep-learning methods are outlined in black, across every licence colour.
    edges = ["#1F2933" if r["category"] == "dl-model" else "none" for r in rows]

    ax_n.set_xlim(0, 1)
    for yi, r in zip(y, rows):
        ref = r["tool_id"] not in in_agg
        col = "#999999" if ref else "#222222"
        label = fs.tool_label(r["name"]) + ("*" if ref else "")
        ax_n.text(1.0, yi, label, ha="right", va="center", fontsize=6.6, color=col)
    if n_ref:
        cut = (y[-n_ref] + y[-n_ref - 1]) / 2
        for ax in axes:
            ax.axhline(cut, color="#bbbbbb", lw=0.6, ls="-", xmin=0, xmax=1, clip_on=False)
    ax_n.axis("off")

    ax_count.barh(y, [r["last"] for r in rows], left=1, height=0.62, color=colours, edgecolor=edges, lw=0.7, zorder=3)
    for yi, r in zip(y, rows):
        ax_count.text(r["last"] * 1.25, yi, f"{int(r['last']):,}", va="center", fontsize=5.8,
                      color="#999999" if r["tool_id"] not in in_agg else "#333333")
    ax_count.set_xlim(1, 3e6)
    ax_count.set_xscale("log")
    analysis = set(fs.analysis_tools())
    lead = sorted((r for r in rows if r["tool_id"] in analysis), key=lambda r: -r["last"])
    ax_count.set_title("Papers mentioning each analysis\npackage (2025)", loc="left", fontsize=8)
    ax_count.set_xlabel("Papers mentioning the package (log scale)", fontsize=7.5)
    ax_count.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    fs.sparse_log_ticks(ax_count, [r["last"] for r in rows], n=4)

    for yi, r, c, e in zip(y, rows, colours, edges):
        g = r["growth"]
        ring = e != "none"
        if np.isnan(g) or g <= 0:
            ax_share.scatter([1.0], [yi], s=20, facecolor="white", edgecolor="#999999", lw=0.8, ls="--", zorder=3)
            if ring:
                ax_share.scatter([1.0], [yi], s=60, facecolor="none", edgecolor=e, lw=0.7, zorder=5)
            ax_share.annotate(f"no papers in {GROWTH_FROM}", (1.0, yi), xytext=(8, 0),
                              textcoords="offset points", fontsize=5.6, color="#777777", ha="left", va="center")
            continue
        fragile = r["base"] < FRAGILE
        ax_share.plot([1.0, g], [yi, yi], color="#E3E3E3" if fragile else "#CCCCCC", lw=1.2, zorder=1)
        if fragile:
            ax_share.scatter([g], [yi], s=26, facecolor="white", edgecolor=c, lw=0.9, zorder=4)
        else:
            ax_share.scatter([g], [yi], s=26, color=c, zorder=4)
        if ring:
            ax_share.scatter([g], [yi], s=60, facecolor="none", edgecolor=e, lw=0.7, zorder=5)
        pad = 1.4 if ring else 1.22
        ax_share.text(max(g, 1.0) * pad if g >= 1 else pad, yi, f"{g:.0f}× (from {int(r['base']):,})" if g >= 10 else f"{g:.1f}× (from {int(r['base']):,})",
                      fontsize=5.3, color="#777777" if r["base"] < FRAGILE else "#555555", ha="left", va="center")
    ax_share.axvline(1.0, color="#666666", lw=0.8, ls="--", zorder=2)
    ax_share.set_xscale("log")
    grown = [r for r in rows if r["tool_id"] in in_agg and not np.isnan(r["growth"])]
    top = max((r for r in grown if r["base"] >= FRAGILE), key=lambda r: r["growth"], default=max(grown, key=lambda r: r["growth"]))
    ax_share.set_xlim(min(0.8, min(r["growth"] for r in grown) * 0.7), max(r["growth"] for r in grown) * 12)
    ax_share.set_title(f"{fs.tool_label(top['name'])} grew fastest ({top['growth']:.0f}×) of packages\nwith {FRAGILE}+ papers in {GROWTH_FROM}", loc="left", fontsize=8)
    ax_share.set_xlabel(f"Fold change, {LAST} against {GROWTH_FROM} (log scale)", fontsize=7.5)
    ax_share.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))

    for ax in (ax_count, ax_share):
        ax.grid(axis="x", color="#e3e9ee", lw=0.5)
        ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", labelsize=7)
    ax_count.set_yticks([])
    ax_count.set_ylim(y.min() - 0.8, y.max() + 0.8)

    handles = [plt.Line2D([], [], marker="o", ls="", color=fs.licence_colour(k), label=lab, markersize=5)
               for k, lab in (("library", "open source"), ("commercial", "commercial package"),
                              ("acquisition-suite", "microscope-control program"))]
    handles.append(plt.Line2D([], [], marker="o", ls="", mfc="none", mec="#1F2933", mew=0.7, markersize=7,
                              label="deep-learning method"))
    with warnings.catch_warnings():
        warnings.filterwarnings(
            'ignore', category=UserWarning,
            message='This figure includes Axes that are not compatible with tight_layout, so results might be incorrect[.]')
        fig.tight_layout()
    fig.legend(handles=handles, loc="upper center", ncol=4, fontsize=6.2, frameon=False,
               bbox_to_anchor=(0.5, -0.06), handletextpad=0.2, columnspacing=0.7, borderaxespad=0.1)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "Figure2__landscape", out_dir=out_dir)


if __name__ == "__main__":
    main()
