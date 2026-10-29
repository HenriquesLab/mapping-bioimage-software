"""Figure 6: how deep learning reaches microscopy papers.

(a) Summed dedicated-method matches per 1,000 core analysis-package matches.
(b) Title/abstract lexicon-positive shares, with sampling intervals for
sampled tools; classification uncertainty remains. (c) Host co-mentions.
(d) How Cellpose, StarDist and ilastik were run in three disjoint random samples of
40 papers mentioning the method and ImageJ/Fiji: labels on which two independent
annotators agreed, pooled (data/processed/<method>_workflow_2025_pooled.csv; Cellpose
in cellpose_workflow_pooled_2025.csv).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402

YEAR = 2025
MIN_MATCHES = 100
DL = fs.CATEGORY_COLOR["dl-model"]
DL_LIGHT = "#F0A877"
MEASURE = "#3F4A55"
HOSTS = [("imagej", "ImageJ/Fiji"), ("qupath", "QuPath"), ("napari", "napari")]
# (label key, legend text, colour) in stacking order
WORKFLOW = [
    ("separate", "run on its own", MEASURE),
    ("inside_fiji", "run inside Fiji", DL),
    ("other_pipeline", "run inside other software", DL_LIGHT),
    ("unclear", "combination not stated", "#C3C9D0"),
    ("mention_only", "mentioned without use", "#E3E7EB"),
]
POOLED = [("Cellpose", "cellpose_workflow_pooled_2025.csv"), ("StarDist", "stardist_workflow_2025_pooled.csv"),
          ("ilastik\n(machine learning)", "ilastik_workflow_2025_pooled.csv")]


def _style(ax, axis="y"):
    ax.grid(axis=axis, color="#e8edf1", lw=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=6.5)


def build_figure():
    fs.set_style()
    names = fs.load("tools.csv").set_index("tool_id")["name"].to_dict()
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 5.3),
                             gridspec_kw={"width_ratios": [1, 1.1], "hspace": 0.62, "wspace": 0.62})
    (ax_a, ax_b), (ax_c, ax_d) = axes

    # a: papers naming a deep-learning method, per 1,000 core-package papers
    lit = fs.europepmc_yearly().pivot(index="year", columns="tool_id", values="count")
    named = 10.0 * fs.named_dl_share().sum(axis=1).loc[2015:]
    two = lit.loc[YEAR, ["cellpose", "stardist"]].sum() / lit.loc[YEAR, fs.NAMED_DL].sum()
    ax_a.fill_between(named.index, named.values, color=DL, alpha=0.12, lw=0)
    ax_a.plot(named.index, named.values, marker="o", ms=2.8, color=DL, lw=1.4)
    ax_a.annotate(f"{named.loc[YEAR]:.0f} per 1,000", xy=(YEAR, named.loc[YEAR]), xytext=(-4, 10),
                  textcoords="offset points", ha="right", fontsize=6.4, color=DL)
    # three short lines in the empty top-left corner, clear of the curve
    ax_a.text(2015.3, named.max() * 1.15, f"Cellpose and StarDist:\n{100 * two:.0f}% of matches for the four\ntracked deep-learning methods ({YEAR})",
              fontsize=6.2, color="#555555", va="top")
    ax_a.set_xlim(2014.6, 2025.6)
    ax_a.set_ylim(0, named.max() * 1.25)
    ax_a.set_ylabel("Deep-learning method mentions\nper 1,000 core-package mentions", fontsize=6.8)
    ax_a.set_title(f"Deep-learning method mentions rose from\n{named.loc[2020]:.0f} to {named.loc[YEAR]:.0f} per 1,000 ({2020}-{YEAR})", loc="left", fontsize=7.6)
    fs.format_year_ticks(ax_a, max_ticks=5)
    _style(ax_a)

    # b: deep-learning vocabulary in each core package's abstracts, 2025
    est = fs.load("dl_estimates.csv")
    est = est[(est["year"] == YEAR) & est["tool_id"].isin(fs.analysis_tools())]
    base = lit.loc[YEAR]
    est = est[est["tool_id"].map(base) >= MIN_MATCHES].copy()
    est["p"], est["lo"], est["hi"] = 100 * est["dl_fraction"], 100 * est["ci_lo"], 100 * est["ci_hi"]
    est = est.sort_values("p")
    y = np.arange(len(est))
    cols = [DL if names[t] in ("Cellpose", "StarDist") else MEASURE for t in est["tool_id"]]
    ax_b.hlines(y, est["lo"], est["hi"], color=MEASURE, lw=1.1, alpha=0.45)
    ax_b.scatter(est["p"], y, s=20, color=cols, zorder=5)
    for yi, v in zip(y, est["p"]):
        ax_b.annotate(fs.pct(v), (v, yi), xytext=(8, 0), textcoords="offset points",
                      fontsize=5.8, color="#555555", ha="left", va="center", zorder=6)
    ax_b.set_yticks(y, [fs.tool_label(names[t]) for t in est["tool_id"]], fontsize=6.6)
    ax_b.set_xlabel("Titles/abstracts matching deep-learning vocabulary (%)", fontsize=6.8)
    ax_b.set_xlim(-0.5, max(25, float(est["hi"].max()) + 4))
    ax_b.spines["left"].set_visible(False)
    ax_b.tick_params(axis="y", length=0)
    ax_b.set_title(f"Even in Cellpose and StarDist papers, few\nabstracts mention deep learning ({YEAR})", loc="left", fontsize=7.6)
    _style(ax_b, "x")

    # c: host platforms named alongside Cellpose and StarDist
    h = fs.load("dl_host_comentions.csv")
    h = h[h["year"] == YEAR]
    x = np.arange(len(HOSTS))
    w = 0.36
    for i, (dl, lab, col) in enumerate([("cellpose", "Cellpose", DL), ("stardist", "StarDist", DL_LIGHT)]):
        sub = h[h["dl_tool"] == dl].set_index("host")
        vals = [100 * sub.loc[k, "share_host"] for k, _ in HOSTS]
        bars = ax_c.bar(x + (i - 0.5) * w, vals, w, color=col, zorder=3,
                        label=f"{lab} (n = {int(sub['n_dl'].iloc[0]):,})")
        for b, v in zip(bars, vals):
            ax_c.text(b.get_x() + b.get_width() / 2, v + 1.5, fs.pct(v), ha="center", va="bottom", fontsize=6.4)
    ax_c.set_xticks(x, [n for _, n in HOSTS], fontsize=7)
    ax_c.set_ylim(0, 100)
    ax_c.set_ylabel("Papers that also mention the host (%)", fontsize=6.8)
    ax_c.legend(fontsize=6.4, frameon=False, loc="upper right")
    ax_c.set_title(f"Cellpose and StarDist papers also mention\nImageJ/Fiji, QuPath or napari ({YEAR})", loc="left", fontsize=7.6)
    _style(ax_c)

    # d: how each method was run in papers also mentioning ImageJ/Fiji, three samples of 40, agreed labels pooled
    rows = np.arange(len(POOLED))[::-1]
    for yi, (label, f) in zip(rows, POOLED):
        n = pd.read_csv(fs.PROCESSED / f).set_index("category")["pooled"]
        left = 0.0
        for k, _, colour in WORKFLOW:
            w = 100 * n[k] / n["agreed"]
            ax_d.barh(yi, w, left=left, color=colour, height=0.62, zorder=3)
            if w >= 8:
                ax_d.text(left + w / 2, yi, f"{w:.0f}", fontsize=6.4, ha="center", va="center",
                          color="white" if colour in (MEASURE, DL) else fs.INK, zorder=4)
            left += w
        ax_d.text(101, yi, f"{int(n['agreed'])}/{int(n['labelled'])}", fontsize=6.2, va="center", color="#5F6B7A")
    ax_d.set_yticks(rows, [l for l, _ in POOLED], fontsize=6.8)
    ax_d.set_xlim(0, 100)
    ax_d.set_xlabel("Papers with agreed labels (%)", fontsize=6.8)
    ax_d.spines["left"].set_visible(False)
    ax_d.tick_params(axis="y", length=0)
    ax_d.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in WORKFLOW], labels=[t for _, t, _ in WORKFLOW],
                fontsize=6.2, frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(-0.02, -0.2),
                handlelength=1.0, columnspacing=0.8)
    ax_d.set_title(f"How each method was run in papers\nthat also mention ImageJ/Fiji ({YEAR})", loc="left", fontsize=7.6)
    _style(ax_d, "x")

    for ax, letter, xo in [(ax_a, "a", -0.3), (ax_b, "b", -0.36), (ax_c, "c", -0.3), (ax_d, "d", -0.3)]:
        fs.panel_label(ax, letter, x=xo, y=1.14)
    fig.subplots_adjust(left=0.1, right=0.98, bottom=0.09, top=0.91)
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "Figure6__deep_learning", out_dir=out_dir)


if __name__ == "__main__":
    main()
