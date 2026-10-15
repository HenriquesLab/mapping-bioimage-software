"""Shared publication style and offline data access for the figure modules.

Paths come from the pipeline's _paths module. Figures read processed CSVs,
never live APIs. Outputs use the manuscript mount or figures/output/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

if "--show" not in sys.argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402
import pandas as pd  # noqa: E402

from census._paths import FIGURES_DIR, PROCESSED_DIR, SCRIPTS_DIR

PROCESSED = PROCESSED_DIR


def default_output_dir() -> Path:
    """Use the manuscript mount when present, otherwise a local output folder."""
    return FIGURES_DIR if FIGURES_DIR.is_dir() else SCRIPTS_DIR / "figures" / "output"


FIG_DIR = default_output_dir()

# Colour-blind-safe palette (Okabe-Ito), assigned per tool where relevant.
PALETTE = {
    "imagej": "#0072B2",
    "napari": "#009E73",
    "jupyter": "#E69F00",
    "cellprofiler": "#56B4E9",
    "qupath": "#CC79A7",
    "cellpose": "#D55E00",
    "stardist": "#C99A0A",  # darker than Okabe-Ito yellow, which vanishes on white
    "matlab": "#999999",
}
CATEGORY_COLOR = {
    "notebook": "#E69F00",
    "general-platform": "#0072B2",
    "dl-model": "#D55E00",
    "commercial": "#999999",
    "library": "#009E73",
    "acquisition-suite": "#8C6BB1",
}
CATEGORY_LABEL = {
    "general-platform": "open platform",
    "dl-model": "deep-learning method",
    "notebook": "notebook",
    "library": "Python library",
    "commercial": "commercial package",
    "acquisition-suite": "microscope-control program",
}
OPEN_CATEGORIES = ("general-platform", "dl-model", "notebook", "library")


def licence_colour(category: str) -> str:
    """Blue for open-source packages; commercial and microscope-control software keep their own colours."""
    return CATEGORY_COLOR["general-platform"] if category in OPEN_CATEGORIES else CATEGORY_COLOR.get(category, "#444444")


INK = "#262626"       # titles and data labels
MUTED = "#6B6B6B"     # axis labels, ticks, annotations
GRID = "#ECECEC"


def set_style() -> None:
    """Journal figure style: Arial at print sizes, light structure, editable text."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            # Arial first: matplotlib cannot read the bold face inside macOS's
            # Helvetica .ttc collection, so bold titles silently fall back to regular.
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 7,
            "text.color": INK,
            "axes.titlesize": 8,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlepad": 6,
            "axes.labelsize": 7,
            "axes.labelcolor": MUTED,
            "axes.linewidth": 0.6,
            "axes.edgecolor": "#8A8A8A",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.axisbelow": True,
            "axes.grid": False,
            "grid.color": GRID,
            "grid.linewidth": 0.5,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.minor.size": 1.5,
            "ytick.minor.size": 1.5,
            "lines.linewidth": 1.4,
            "lines.markersize": 4,
            "patch.linewidth": 0,
            "legend.frameon": False,
            "legend.fontsize": 6.5,
            "legend.handlelength": 1.2,
            "legend.handletextpad": 0.5,
            "legend.borderaxespad": 0.2,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.pad_inches": 0.03,
            "pdf.fonttype": 42,   # TrueType: text stays editable in Illustrator
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def load(name: str) -> pd.DataFrame:
    path = PROCESSED / name
    if not path.exists():
        raise SystemExit(
            f"missing {path.name}; run `python -m census.build.build_dataset` first"
        )
    return pd.read_csv(path)


def format_year_ticks(ax, max_ticks: int | None = None) -> None:
    """Render calendar-year ticks as integers, with optional density control."""
    kwargs = {"integer": True, "min_n_ticks": 4}
    if max_ticks is not None:
        kwargs["nbins"] = max_ticks
    ax.xaxis.set_major_locator(MaxNLocator(**kwargs))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}"))


def europepmc_yearly() -> pd.DataFrame:
    """Europe PMC yearly tool-paper matches for every registry tool."""
    lit = load("literature_yearly.csv")
    return lit[lit["source"] == "europepmc"][["tool_id", "year", "count"]].reset_index(drop=True)


def dl_in_tool_yearly() -> pd.DataFrame:
    """Strict estimator: papers naming the tool AND a deep-learning term in full text.

    Covers imagej, napari and jupyter only. Read as a lower bound on the share of
    a tool's papers that use deep learning; the lexicon fraction is the upper bound.
    """
    df = load("dl_in_tools_yearly.csv")
    if "query_kind" in df:
        df = df[df["query_kind"] == "dl_in_tool"]
    return df[["tool_id", "year", "count"]]


def dl_in_tool_share() -> pd.DataFrame:
    """Second estimator as a percent: DL-term papers over the matching tool base.

    Both counts use the same tool clause and the same research-article filter,
    so reviews and preprints drop out of numerator and denominator alike.
    """
    df = load("dl_in_tools_yearly.csv")
    if "query_kind" not in df or not (df["query_kind"] == "tool_base").any():
        return pd.DataFrame(columns=["tool_id", "year", "share"])
    w = df.pivot_table(index=["tool_id", "year"], columns="query_kind", values="count")
    w = w[w["tool_base"] > 0]
    out = (100.0 * w["dl_in_tool"] / w["tool_base"]).rename("share").reset_index()
    return out


NAMED_DL = ["cellpose", "stardist", "deepimagej", "zerocostdl4mic"]


def corpus() -> pd.Series:
    """Yearly count of all microscopy papers in Europe PMC (reach denominator)."""
    return load("corpus_yearly.csv").set_index("year")["microscopy_papers"]


def reach(tool_ids) -> pd.Series:
    """Percent of all microscopy papers naming any of ``tool_ids`` (summed).

    Summing several tools double-counts papers naming more than one, so a
    multi-tool series is an upper bound.
    """
    df = europepmc_yearly()
    num = df[df["tool_id"].isin(list(tool_ids))].groupby("year")["count"].sum()
    return 100.0 * num / corpus().reindex(num.index)


def dedicated_total() -> pd.Series:
    """Yearly matches summed over the core tools, the deep-learning denominator."""
    df = europepmc_yearly()
    return df[df["tool_id"].isin(core_tools())].groupby("year")["count"].sum()


def named_dl_share() -> pd.DataFrame:
    """Each named deep-learning tool's share of dedicated-tool matches, percent."""
    df = europepmc_yearly()
    wide = df[df["tool_id"].isin(NAMED_DL)].pivot(index="year", columns="tool_id", values="count")
    return 100.0 * wide[NAMED_DL].div(dedicated_total(), axis=0)


def field_dl() -> pd.DataFrame:
    """Field-level lexicon deep-learning share with its 95% interval, percent."""
    f = load("dl_field_yearly.csv").sort_values("year").copy()
    for c in ("dl_share", "dl_share_lo", "dl_share_hi"):
        if c in f:
            f[c] = 100.0 * f[c]
    return f


SHORT_LABEL = {"ZeroCostDL4Mic/DL4MicEverywhere": "ZCDL4M/DL4ME"}  # long names abbreviated in figures; legends spell them out


def tool_label(name: str) -> str:
    name = name.replace(" / ", "/")
    return SHORT_LABEL.get(name, name)


def pct(v: float) -> str:
    """Percentage label as a whole number; below 0.5% prints as <1% (no decimals)."""
    if 0 < v < 0.5:
        return "<1%"
    return f"{int(v + 0.5)}%"


def aggregate_tools() -> list[str]:
    """Registry tools counted in field aggregates (MATLAB and Jupyter notebooks are references)."""
    tools = load("tools.csv")
    return tools.loc[tools["in_aggregate"].astype(str).str.lower() == "true", "tool_id"].tolist()


def core_tools() -> list[str]:
    """The 13 core analysis tools chosen at the start of the study (registry
    scope 'core'), the denominator of the named deep-learning series."""
    tools = load("tools.csv").set_index("tool_id")
    scope = tools["scope"] if "scope" in tools else pd.Series("core", index=tools.index)
    return [t for t in aggregate_tools() if scope.get(t, "core") == "core"]


def analysis_tools() -> list[str]:
    """Aggregate tools without the microscope-control programs, whose mentions
    often describe image acquisition only."""
    cat = load("tools.csv").set_index("tool_id")["category"]
    return [t for t in aggregate_tools() if cat.get(t) != "acquisition-suite"]


def share_of_total(group: str = "analysis") -> pd.DataFrame:
    """Per-tool share of yearly tool-paper matches, in percent.

    group 'analysis' divides by the analysis tools; 'all' adds the
    microscope-control programs. MATLAB and Jupyter notebooks enter neither.
    """
    ids = analysis_tools() if group == "analysis" else aggregate_tools()
    df = europepmc_yearly()
    df = df[df["tool_id"].isin(ids)]
    totals = df.groupby("year")["count"].transform("sum")
    out = df.copy()
    out["share"] = 100.0 * out["count"] / totals
    return out



def sparse_log_ticks(ax, values, n: int = 3) -> None:
    """Pick at most n decade ticks spanning the data, so labels never collide."""
    import numpy as _np
    v = [x for x in values if x and x > 0]
    if not v:
        return
    lo, hi = int(_np.floor(_np.log10(min(v)))), int(_np.ceil(_np.log10(max(v))))
    decades = list(range(lo, hi + 1))
    if len(decades) > n:
        step = max(1, round(len(decades) / n))
        decades = decades[::step]
    ax.set_xticks([10.0 ** d for d in decades])


def panel_label(ax, letter: str, x: float = -0.22, y: float = 1.04) -> None:
    """Bold lowercase panel letter outside the top-left corner (NC style)."""
    ax.text(x, y, letter, transform=ax.transAxes, fontsize=9.5, fontweight="bold",
            color=INK, va="bottom", ha="left")


def save(fig, stem: str, out_dir=None) -> None:
    """Save the unchanged publication rendering in all three formats."""
    out_dir = default_output_dir() if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(out_dir / f"{stem}.{ext}", bbox_inches="tight")
    if "--show" in sys.argv:
        plt.show()
    print(f"wrote {stem}.png/.pdf/.svg")
