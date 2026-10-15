"""Figure 4: reach and concentration.

Panel a gives the share of full-text microscopy papers mentioning ImageJ/Fiji,
any of the 22 analysis packages, any of the other 21, and any microscope-control
program; grouped curves count each paper once (build_reach_any.py). Panel b shows concentration within the tracked registry, with
and without microscope-control programs.
"""

from __future__ import annotations

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402

FROM, TO = 2020, 2025
N_GAINERS = 10
IJ = fs.PALETTE["imagej"]
OTHER = "#6b7c8c"
VENDOR = fs.CATEGORY_COLOR["acquisition-suite"]
ANY = "#1F2933"


def build_figure():
    fs.set_style()
    analysis = fs.analysis_tools()
    others = [t for t in analysis if t != "imagej"]

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.1, 2.8))

    # a: reach, share of all full-text microscopy papers
    grp = fs.load("reach_any_yearly.csv").pivot(index="year", columns="group", values="papers")
    grp = grp.div(fs.corpus().reindex(grp.index), axis=0) * 100
    series = [(grp["analysis"], ANY, f"any of the {len(analysis)} analysis packages"),
              (fs.reach(["imagej"]), IJ, "ImageJ/Fiji"),
              (grp["other_analysis"], OTHER, f"any of the {len(others)} other analysis packages"),
              (grp["microscope_control"], VENDOR, "any of the 6 microscope-control programs")]
    for s, c, lab in series:
        ax_a.plot(s.index, s.values, marker="o", ms=2.3, color=c, lw=1.2,
                  ls="--" if c == VENDOR else ":" if c == ANY else "-", label=lab.replace("\n", " "))
        ax_a.annotate(fs.pct(s.iloc[-1]), xy=(s.index[-1], s.iloc[-1]), xytext=(3, {ANY: 4, IJ: -3, VENDOR: 2, OTHER: -2}[c]),
                      textcoords="offset points", fontsize=6.2, color=c, va="center")
        ax_a.annotate(fs.pct(s.iloc[0]), xy=(s.index[0], s.iloc[0]), xytext=(-3, {ANY: 6, IJ: 0, VENDOR: -6, OTHER: -3}[c]),
                      textcoords="offset points", fontsize=6.2, color=c, ha="right", va="center")
    r_any = series[0][0]
    ax_a.legend(loc="upper left", fontsize=5.8, handlelength=1.8, labelspacing=0.3, borderaxespad=0.1)
    ax_a.set_ylim(0, r_any.max() * 1.45)
    ax_a.set_xlim(2008.6, 2027)
    ax_a.set_ylabel("Full-text microscopy papers\nmentioning the software (%)", fontsize=7)
    ax_a.set_title(f"{fs.pct(r_any.iloc[-1])} of microscopy papers mention\nan analysis package ({TO})", loc="left", fontsize=7.6)

    # b: concentration, ImageJ/Fiji share of package mentions
    shares = {}
    for group, ls, lab in [("analysis", "-", f"{len(analysis)} analysis packages"),
                           ("all", "--", "including microscope-control\nsoftware (ZEN, NIS-Elements, LAS X...)")]:
        sh = fs.share_of_total(group)
        sh = sh[sh["tool_id"] == "imagej"].set_index("year")["share"]
        ax_b.plot(sh.index, sh.values, marker="o", ms=2.3, color=IJ, lw=1.2, ls=ls,
                  alpha=1.0 if ls == "-" else 0.75)
        ax_b.annotate(fs.pct(sh.iloc[0]), xy=(sh.index[0], sh.iloc[0]), xytext=(0, 6 if ls == "-" else -9),
                      textcoords="offset points", fontsize=6.2, color=IJ, ha="center", va="center")
        shares[group] = sh
        ax_b.annotate(fs.pct(sh.iloc[-1]), xy=(sh.index[-1], sh.iloc[-1]), xytext=(3, 0),
                      textcoords="offset points", fontsize=6.2, color=IJ, va="center")
        ax_b.text(2017.5 if ls == "-" else 2019.5, sh.loc[2017] + 6 if ls == "-" else sh.loc[2019] - 20, "among " + lab if ls == "-" else lab,
                  fontsize=6.0, color=IJ, ha="center")
    ax_b.set_ylim(0, 100)
    ax_b.set_xlim(2008.6, 2027)
    ax_b.set_ylabel("ImageJ/Fiji share of\npackage mentions (%)", fontsize=7)
    a = shares["analysis"]
    ax_b.set_title(f"ImageJ/Fiji accounts for {fs.pct(a.loc[TO])} of\nmentions of tracked analysis packages", loc="left", fontsize=7.6)

    for ax in (ax_a, ax_b):
        fs.format_year_ticks(ax, max_ticks=4)
        ax.tick_params(labelsize=6.5)
        ax.grid(axis="y", color="#e8edf1", lw=0.5)
        ax.set_axisbelow(True)

    for ax, letter, x in [(ax_a, "a", -0.3), (ax_b, "b", -0.3)]:
        fs.panel_label(ax, letter, x=x, y=1.12)
    fig.subplots_adjust(left=0.1, right=0.97, bottom=0.15, top=0.83, wspace=0.42)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "Figure4__reach", out_dir=out_dir)


if __name__ == "__main__":
    main()
