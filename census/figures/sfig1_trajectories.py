"""Supplementary Figure 1: every package's trajectory, as reach.

Each panel divides the package's yearly matches by every full-text microscopy
paper that year, so literature growth cancels and the lines are comparable in kind. The
vertical scales differ by three orders of magnitude, so each panel prints its
own maximum.
"""

from __future__ import annotations

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402


def _fmt(v: float) -> str:
    return f"{v:.2g}%" if v < 1 else fs.pct(v)


def build_figure():
    fs.set_style()
    tools = fs.load("tools.csv").set_index("tool_id")
    counts = fs.europepmc_yearly()
    by_year = counts.set_index(["tool_id", "year"])["count"]
    order = [t for t in tools.index if t in set(counts["tool_id"]) and t != "nihimage"]
    order.sort(key=lambda t: (t not in fs.aggregate_tools(), -float(by_year.get((t, 2025), 0))))

    ncol = 5
    nrow = -(-len(order) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(7.1, (1.25 * nrow + 0.5) * 0.95))
    for i, (ax, tool) in enumerate(zip(axes.flat, order)):
        s = fs.reach([tool])
        colour = fs.licence_colour(tools.loc[tool, "category"])
        line = "#1F2933" if tools.loc[tool, "category"] == "dl-model" else colour  # deep-learning methods outlined in black
        if tool not in fs.aggregate_tools():
            colour = "#bbbbbb"
        ax.fill_between(s.index, s.values, color=colour, alpha=0.22, lw=0)
        ax.plot(s.index, s.values, color=line if tool in fs.aggregate_tools() else colour, lw=1.2)
        name = fs.tool_label(tools.loc[tool, "name"]) + ("*" if tool not in fs.aggregate_tools() else "")
        ax.set_title(name, loc="left", fontsize=7, pad=2)
        peak = float(s.max())
        ax.set_ylim(0, peak * 1.25 if peak > 0 else 1)
        ax.set_xlim(2010, 2025)
        ax.set_xticks([2010, 2015, 2020, 2025], ["'10", "'15", "'20", "'25"])
        ax.tick_params(labelsize=5.5, length=1.5)
        ax.grid(axis="x", color="#e8edf1", lw=0.4, ls=":")
        ax.set_yticks([0, peak] if peak > 0 else [0], ["0", _fmt(peak)] if peak > 0 else ["0"],
                      fontsize=5.8)
    for ax in list(axes.flat)[len(order):]:
        ax.axis("off")
    fig.supylabel("Full-text microscopy papers mentioning the package (%)", fontsize=7)
    fig.tight_layout(h_pad=1.2, w_pad=0.6)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "SFigure1__trajectories", out_dir=out_dir)


if __name__ == "__main__":
    main()
