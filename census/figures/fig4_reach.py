"""Figure 4: reach of the analysis packages.

One panel: the share of full-text microscopy papers mentioning any of the
analysis packages, ImageJ/Fiji, and any of the others; grouped curves count each
paper once (build_reach_any.py).
"""

from __future__ import annotations

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402

TO = 2025
IJ = fs.PALETTE["imagej"]
OTHER = "#6b7c8c"
ANY = "#1F2933"


def build_figure():
    fs.set_style()
    analysis = fs.analysis_tools()

    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    grp = fs.load("reach_any_yearly.csv").pivot(index="year", columns="group", values="papers")
    grp = grp.div(fs.corpus().reindex(grp.index), axis=0) * 100
    series = [(grp["analysis"], ANY, ":", "all together"),
              (fs.reach(["imagej"]), IJ, "-", "ImageJ/Fiji"),
              (grp["other_analysis"], OTHER, "-", "all minus ImageJ/Fiji")]
    for s, c, ls, lab in series:
        ax.plot(s.index, s.values, marker="o", ms=2.3, color=c, lw=1.2, ls=ls)
        # direct labels at both ends replace the legend
        ax.annotate(f"{lab} {fs.pct(s.iloc[-1])}", xy=(s.index[-1], s.iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=6.2, color=c, va="center")
        ax.annotate(fs.pct(s.iloc[0]), xy=(s.index[0], s.iloc[0]), xytext=(-4, 0),
                    textcoords="offset points", fontsize=6.2, color=c, ha="right", va="center")
    r_any = series[0][0]
    ax.set_ylim(0, r_any.max() * 1.15)
    ax.set_xlim(2006.5, 2025)
    ax.set_ylabel("Microscopy papers\nmentioning the software (%)", fontsize=7)
    ax.set_title(f"Mentions of analysis packages doubled,\nmostly through ImageJ/Fiji ({fs.pct(r_any.iloc[0])} to {fs.pct(r_any.loc[TO])})",
                 loc="left", fontsize=7.6)
    fs.format_year_ticks(ax, max_ticks=4)
    ax.tick_params(labelsize=6.5)
    ax.grid(axis="y", color="#e8edf1", lw=0.5)
    ax.set_axisbelow(True)
    ax.spines["right"].set_visible(False)
    ax.set_clip_on(False)
    fig.subplots_adjust(left=0.16, right=0.7, bottom=0.12, top=0.84)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "Figure4__reach", out_dir=out_dir)


if __name__ == "__main__":
    main()
