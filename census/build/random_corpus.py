"""Random-sample abstract corpus for the research-area analysis.

Reuses the samples drawn for the deep-learning estimate (same seed and
per-package cap, so the records come from the cache) for 2021-2025, the window
in which every main registry package exists. Writes one row per sampled paper,
with the package-year population so estimates can be weighted.

    python -m census.build.random_corpus
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yaml

from census._paths import PROCESSED_DIR, TOOLS_YML, ensure_dirs  # noqa: E402
from census._registry import load_registry  # noqa: E402
from census.sources import europepmc  # noqa: E402

YEARS = range(2021, 2026)
DEFAULT_CAP = 200


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--replicates', action='store_true', help='write new disjoint replicate outputs only')
    args = ap.parse_args()
    if args.replicates:
        from census.validation.replicates import abstracts
        abstracts(years=list(YEARS))
        return
    ensure_dirs()
    reg = load_registry()
    caps = {t["id"]: int(t.get("dl_sample_cap", DEFAULT_CAP))
            for t in yaml.safe_load(TOOLS_YML.read_text())["tools"]}
    jobs = [(t, y) for t in reg.tools for y in YEARS]  # every tool's papers are read

    def one(ty):
        tool, year = ty
        works, population = europepmc.random_sample_works(tool, reg, year, caps.get(tool.id, DEFAULT_CAP))
        return [{**w, "population": population, "n_sampled": len(works)} for w in works]

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for chunk in ex.map(one, jobs) for r in chunk]
    df = pd.DataFrame(rows)[["tool_id", "year", "epmc_id", "population", "n_sampled", "venue", "title", "abstract"]]
    df.to_csv(PROCESSED_DIR / "random_sample_2021_2025.csv.gz", index=False)
    print(df.groupby("tool_id").size().to_string())


if __name__ == "__main__":
    main()
