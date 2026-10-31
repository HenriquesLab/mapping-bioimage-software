"""Figure 1: overview of the study and its findings.

A schematic first figure in the lab's style (mAIcrobe, VLab4Mic), drawn as soft
cards: (a) the microscopy literature and the package registry; (b) papers naming
each of the 23 analysis packages in 2025, ranked on a log scale with every package
labelled; (c) for the six packages in the reporting audit, the share of papers naming each
without citing its papers (2021-2025) and the share whose sentences naming it give no version,
function or parameter (2025). Numbers and sizes come from the processed CSVs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import style as fs
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon  # noqa: E402

W, H = 3.45, 5.0
ASPECT = W / H          # a circle of x-radius r spans r * ASPECT in y
INK = "#1F2933"
SUB = "#5F6B7A"
CARD = "#F3F5F8"
# Blue for open-source packages, grey for commercial ones, slate for icons and text;
# deep-learning methods carry a black ring (fs.licence_colour).
BLUE = fs.CATEGORY_COLOR["general-platform"]
SLATE = "#4A5868"
GREY_C = fs.CATEGORY_COLOR["commercial"]


def tint(colour, k=0.82):
    r, g, b = to_rgb(colour)
    return (r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k)


def card(ax, x, y, w, h, fill=CARD):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.018",
                                facecolor=fill, edgecolor="none", zorder=0))


def title(ax, x, y, letter, text, colour=INK):
    ax.add_patch(Ellipse((x + 0.016, y), 0.032, 0.032 * ASPECT, facecolor=colour, edgecolor="none", zorder=3))
    ax.text(x + 0.016, y - 0.001, letter, fontsize=6.6, fontweight="bold", color="white", ha="center", va="center", zorder=4)
    ax.text(x + 0.045, y, text, fontsize=7.8, fontweight="bold", color=INK, ha="left", va="center", zorder=4)


def pill(ax, x, y, text, colour, size=6.0, k=0.84):
    w = 0.018 + 0.0115 * len(text)
    ax.add_patch(FancyBboxPatch((x, y - 0.0125), w, 0.025, boxstyle="round,pad=0,rounding_size=0.0125",
                                facecolor=tint(colour, k), edgecolor="none", zorder=3))
    ax.text(x + w / 2, y, text, fontsize=size, color=colour, fontweight="bold", ha="center", va="center", zorder=4)
    return w


def link(ax, a, b, colour, rad=0.0, head=True, lw=0.9, alpha=1.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>" if head else "-", mutation_scale=6.5, lw=lw,
                                 color=colour, alpha=alpha, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=0, shrinkB=0, zorder=2))


def doc_icon(ax, x, y, w=0.06):
    h = w * 1.25 / ASPECT * 0.55
    for k, a in enumerate((0.35, 0.6, 1.0)):
        dx = 0.010 * (2 - k)
        dy = 0.008 * (2 - k)
        fold = w * 0.28
        pts = [(x + dx, y + dy), (x + dx + w, y + dy), (x + dx + w, y + dy + h - fold * ASPECT),
               (x + dx + w - fold, y + dy + h), (x + dx, y + dy + h)]
        ax.add_patch(Polygon(pts, closed=True, facecolor="white", edgecolor=SUB, lw=0.7, alpha=a, zorder=3 + k))
    for j in range(3):
        ax.plot([x + 0.010, x + w - 0.014], [y + h - 0.022 - j * 0.012] * 2, color=tint(SUB, 0.4), lw=0.7, zorder=7)


def build_figure():
    fs.set_style()
    lit = fs.europepmc_yearly().set_index(["tool_id", "year"])["count"]
    corpus = fs.corpus()

    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # (a) literature -----------------------------------------------------------
    ya, ha = 0.775, 0.21
    card(ax, 0.02, ya, 0.96, ha)
    title(ax, 0.045, ya + ha - 0.028, "a", "Microscopy literature, 2010-2025", SLATE)
    doc_icon(ax, 0.06, ya + 0.075)
    ax.text(0.19, ya + 0.135, "Europe PMC full text", fontsize=6.6, fontweight="bold", color=INK, va="center")
    ax.text(0.19, ya + 0.108, f"{int(corpus.loc[2025]):,} microscopy papers in 2025", fontsize=6.0, color=SUB, va="center")
    n_tools = int((fs.load("tools.csv").tool_id != "nihimage").sum())  # NIH Image is plotted only in the history figure
    ax.text(0.19, ya + 0.086, f"mentions of {n_tools} packages, by year", fontsize=6.0, color=SUB, va="center")
    sp = fig.add_axes((0.70, ya + 0.075, 0.25, 0.075))
    c = corpus.loc[2010:2025]
    sp.fill_between(c.index, 0, c.values, color=tint(SLATE, 0.82), lw=0)
    sp.plot(c.index, c.values, color=SLATE, lw=1.1)
    sp.set_xlim(2010, 2025)
    sp.set_ylim(0, c.max() * 1.45)
    sp.axis("off")
    ax.text(0.95, ya + 0.163, "Microscopy papers per year", fontsize=6.0, color=SUB, va="center", ha="right")
    # Label both ends with their counts and years, so the growth reads directly.
    for yr, ha in ((2010, "left"), (2025, "right")):
        v = c.loc[yr]
        sp.plot([yr], [v], "o", ms=2.2, color=SLATE, clip_on=False, zorder=5)
        sp.text(yr, v + c.max() * 0.13, f"{v / 1000:.0f}k", fontsize=6.0, fontweight="bold", color=INK, ha=ha, va="bottom")
        sp.text(yr, -c.max() * 0.07, str(yr), fontsize=6.0, color=SUB, ha=ha, va="top", clip_on=False)
    tools = [("ImageJ/Fiji", BLUE), ("QuPath", BLUE), ("CellProfiler", BLUE), ("napari", BLUE),
             ("Imaris", GREY_C), ("Cellpose", BLUE), ("StarDist", BLUE), (f"+{n_tools - 7} more", SLATE)]
    x = 0.045
    for name, col in tools:
        x += pill(ax, x, ya + 0.034, name, col, size=6.0) + 0.004
    link(ax, (0.5, ya - 0.004), (0.5, ya - 0.024), SUB, lw=1.0)

    # (b) papers naming each analysis package, ranked ------------------------
    yb, hb = 0.255, 0.49
    card(ax, 0.02, yb, 0.96, hb)
    title(ax, 0.045, yb + hb - 0.028, "b", "Papers mentioning each analysis package, 2025", SLATE)
    reg = fs.load("tools.csv").set_index("tool_id")
    ana = reg[reg["in_aggregate"] & (reg["category"] != "acquisition-suite")].index
    d = pd.DataFrame({"name": reg.loc[ana, "name"].map(fs.tool_label),
                      "category": reg.loc[ana, "category"],
                      "n": [int(lit.get((t, 2025), 0)) for t in ana]}, index=ana).sort_values("n", ascending=False)
    rank = np.arange(1, len(d) + 1)
    ymin, ymax = 2, 4e5
    box = (0.13, yb + 0.05, 0.82, hb - 0.11)
    s = fig.add_axes(box)
    s.set_facecolor("none")
    s.scatter(rank, d["n"].clip(lower=1), c=d["category"].map(fs.licence_colour), s=11, lw=0, zorder=3)
    dl = (d["category"] == "dl-model").to_numpy()
    s.scatter(rank[dl], d["n"][dl], s=34, facecolors="none", edgecolors=INK, lw=0.6, zorder=4)
    s.set_yscale("log")
    s.set_ylim(ymin, ymax)
    s.set_xlim(0.3, len(d) + 0.7)
    # Every package is labelled vertically: below its dot where the log axis leaves room, else above.
    axis_pt = box[3] * H * 72
    fsz = 6.0
    for r, (t, row) in zip(rank, d.iterrows()):
        v = max(row["n"], 1)
        if t == "imagej":
            s.annotate(f"ImageJ/Fiji  {v:,} papers ({fs.pct(fs.reach(['imagej']).loc[2025])} of microscopy papers)",
                       (r, v), xytext=(5, 0), textcoords="offset points", fontsize=6.0, fontweight="bold",
                       color=INK, va="center", ha="left")
            continue
        label = f"{row['name']}  {v:,}"
        need = len(label) * fsz * 0.47 + 4
        below = (np.log(v / ymin) / np.log(ymax / ymin)) * axis_pt > need
        gap = 6 if row["category"] == "dl-model" else 4  # clear the larger deep-learning ring
        s.annotate(label, (r, v), xytext=(0, -gap if below else gap), textcoords="offset points", fontsize=fsz,
                   color=INK, rotation=90, ha="center", va="top" if below else "bottom")
    s.set_xticks([1, 5, 10, 15, 20, len(d)])
    s.tick_params(labelsize=6.0, length=2)
    s.set_xlabel("rank", fontsize=6.0, color=SUB, labelpad=1)
    s.set_ylabel("papers (log scale)", fontsize=6.0, color=SUB, labelpad=4)
    for side in ("top", "right"):
        s.spines[side].set_visible(False)
    link(ax, (0.5, yb - 0.004), (0.5, yb - 0.024), SUB, lw=1.0)

    # (c) named without citation or detail ---------------------------------------
    yc, hc = 0.015, 0.215
    card(ax, 0.02, yc, 0.96, hc)
    title(ax, 0.045, yc + hc - 0.028, "c", "Mentioned without citation or detail", SLATE)
    mc = fs.load("mentions_citations_yearly.csv")
    mc = mc[mc.year.between(2021, 2025)].groupby(["tool_id", "method"])[["named", "cited", "both"]].sum().reset_index()
    mc["nnc"] = 100 * (mc.named - mc.both) / (mc.named + mc.cited - mc.both)
    audit = fs.load("reporting_audit_pooled_2025.csv").set_index("tool_id")
    p = mc.set_index("tool_id").loc[audit.index, ["nnc", "method"]]
    p["name_only"] = audit["name_only_pct"]
    p["label"] = [fs.tool_label(audit.loc[t, "name"]) for t in p.index]
    # citations of napari and StarDist are matched by reference title (no indexed own paper)
    p.loc[p.method.eq("titles"), "label"] += "†"
    p["dl"] = reg.loc[p.index, "category"].eq("dl-model")
    p = p.sort_values("nnc")
    rows = np.arange(len(p))
    for k, (col, head) in enumerate((("nnc", "mentioned, not cited\n(2021-2025)"),
                                     ("name_only", "mentioned without version,\nfunction or parameter (2025)"))):
        b = fig.add_axes((0.20 + k * 0.40, yc + 0.040, 0.33, 0.098))
        b.set_facecolor("none")
        b.barh(rows, p[col], height=0.68, color=BLUE, edgecolor=np.where(p.dl, INK, "none"), lw=0.6,
               hatch=None, zorder=2)
        for r_, v in zip(rows, p[col]):
            b.text(v + 2, r_, f"{v:.0f}%", fontsize=6.0, color=INK, va="center", ha="left")
        b.set_xlim(0, 100)
        b.set_ylim(-0.6, len(p) - 0.4)
        b.set_yticks(rows, p.label if k == 0 else [""] * len(p))
        b.tick_params(axis="y", length=0, labelsize=6.0, pad=2)
        b.set_xticks([])
        for side in ("top", "right", "bottom"):
            b.spines[side].set_visible(False)
        b.spines["left"].set_linewidth(0.5)
        b.set_title(head, fontsize=6.0, color=SUB, loc="left", pad=2, linespacing=1.1)
    ax.text(0.07, yc + 0.022, "† citation matched by name in reference titles; outlined: deep-learning method",
            fontsize=6.0, color=SUB, va="center")
    return fig


def main(out_dir=None) -> None:
    fs.save(build_figure(), "Figure1__overview", out_dir=out_dir)


if __name__ == "__main__":
    main()
