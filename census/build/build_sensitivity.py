"""Sensitivity checks on the headline counts.

Writes two CSVs:

  methods_microscopy_yearly.csv  For every package and year, full-text matches whose
                                 Methods section names both the package and microscopy
                                 (METHODS field), with the matching denominator of
                                 papers whose Methods section names microscopy. This
                                 keeps papers that used the package for microscopy
                                 analysis and drops papers that name it only for
                                 other work, such as gel quantification.
  dl_reference_2025.csv          2025 full-text microscopy papers naming deep-learning
                                 methods and other packages outside the registry, as
                                 a scale reference for the four dedicated
                                 deep-learning methods tracked.

Run with --reference-only to refresh dl_reference_2025.csv alone.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR, ensure_dirs  # noqa: E402
from census._registry import load_registry  # noqa: E402
from census.sources.europepmc import _hit_count  # noqa: E402

METHODS_MICRO = '(METHODS:"microscopy" OR METHODS:"microscope")'
REFERENCE = {
    "U-Net": '("U-Net" OR "UNet")',
    "YOLO": '"YOLO"',
    "Segment Anything": '"Segment Anything"',
    "nnU-Net": '("nnU-Net" OR "nnUNet")',
    "DeepCell": '"DeepCell"',
    "Omnipose": '"Omnipose"',
    "Cellpose-SAM": '"Cellpose-SAM"',
    "Segment Anything for Microscopy": '("micro-sam" OR "micro_sam" OR "μSAM" OR "Segment Anything for Microscopy")',
    "DINOv2": '"DINOv2"',
    "Cell-DINO": '("Cell-DINO" OR "CellDINO")',
}
# Packages outside the registry that are not deep-learning methods, for scale.
OTHER = {
    "TrackMate": '"TrackMate"',
    "Trainable Weka Segmentation": '"Trainable Weka Segmentation"',
    "Squidpy": '"Squidpy"',
}
YEAR = 2025


def _methods(tool) -> str:
    return "(" + " OR ".join(tool.terms("METHODS:")) + ")"


def reference(reg) -> pd.DataFrame:
    refs = {**REFERENCE, **OTHER}
    qs = [f"{q} AND ({reg.context_query}) AND PUB_YEAR:{YEAR}" for q in refs.values()]
    with ThreadPoolExecutor(max_workers=6) as ex:
        counts = list(ex.map(_hit_count, qs))
    r = pd.DataFrame([{"method": k, "kind": "deep-learning" if k in REFERENCE else "other",
                       "year": YEAR, "papers": c} for k, c in zip(refs, counts)])
    r.to_csv(PROCESSED_DIR / "dl_reference_2025.csv", index=False)
    return r


def main() -> None:
    ensure_dirs()
    reg = load_registry()
    if "--reference-only" in sys.argv:
        print(reference(reg).to_string(index=False))
        return
    jobs = {}
    for y in reg.years:
        jobs[("corpus", y)] = f"{METHODS_MICRO} AND HAS_FT:Y AND PUB_YEAR:{y}"
        for t in reg.tools:
            jobs[(t.id, y)] = f"{_methods(t)} AND {METHODS_MICRO} AND HAS_FT:Y AND PUB_YEAR:{y}"
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = dict(zip(jobs, ex.map(_hit_count, jobs.values())))
    rows = []
    for y in reg.years:
        for t in reg.tools:
            rows.append({"tool_id": t.id, "year": y, "count": res[(t.id, y)],
                         "methods_microscopy_papers": res[("corpus", y)]})
    m = pd.DataFrame(rows)
    m.to_csv(PROCESSED_DIR / "methods_microscopy_yearly.csv", index=False)
    r = reference(reg)
    old = PROCESSED_DIR / "imagej_blot_sensitivity.csv"
    if old.exists():
        old.unlink()

    tools = {t.id: t for t in reg.tools}
    analysis = [t.id for t in reg.tools if t.in_aggregate and t.category != "acquisition-suite"]
    allagg = [t.id for t in reg.tools if t.in_aggregate]
    p = m.pivot(index="year", columns="tool_id", values="count")
    corpus = m.groupby("year")["methods_microscopy_papers"].first()
    out = pd.DataFrame({
        "corpus": corpus,
        "imagej_reach_pct": (100 * p["imagej"] / corpus).round(1),
        "others_reach_pct": (100 * p[[t for t in analysis if t != "imagej"]].sum(axis=1) / corpus).round(1),
        "imagej_share_analysis_pct": (100 * p["imagej"] / p[analysis].sum(axis=1)).round(1),
        "imagej_share_all_pct": (100 * p["imagej"] / p[allagg].sum(axis=1)).round(1),
    })
    print(out.loc[[2010, 2015, 2020, 2025]].to_string())
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()
