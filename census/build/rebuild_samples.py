"""Rebuild only the sample-based outputs, leaving the literature counts alone.

Re-draws the deep-learning samples (census up to CENSUS_MAX matches, simple
random sample above it) and the 2021-2025 research-area corpus, then writes
dl_estimates.csv, dl_split_yearly.csv, dl_field_yearly.csv and
random_sample_2021_2025.csv.gz. Literature counts are read from the committed
literature_yearly.csv, so they do not change.

    python -m census.build.rebuild_samples
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR, ensure_dirs  # noqa: E402
from census._registry import load_registry  # noqa: E402
from census.build import build_dataset  # noqa: E402
from census.build import random_corpus  # noqa: E402


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--replicates', action='store_true', help='write new disjoint replicate outputs only')
    args = ap.parse_args()
    if args.replicates:
        from census.validation.replicates import abstracts
        abstracts()
        return
    ensure_dirs()
    reg = load_registry()
    lit = pd.read_csv(PROCESSED_DIR / "literature_yearly.csv")
    build_dataset.build_dl(reg, lit, sample_cap=200)
    print("dl_estimates / dl_split_yearly / dl_field_yearly written", flush=True)
    random_corpus.main()
    print("random_sample_2021_2025.csv.gz written", flush=True)


if __name__ == "__main__":
    main()
