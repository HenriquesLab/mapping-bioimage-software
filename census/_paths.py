"""Canonical paths for the analysis pipeline.

Everything resolves relative to this file, so the pipeline works from any
working directory and in two layouts: as its own repository, and mounted as
the scripts/ submodule of the manuscript repository, which provides
MANUSCRIPT/FIGURES for the figure and SI-table steps.
"""

from __future__ import annotations

from pathlib import Path

# Pipeline root is the parent of this package, scripts/ in the manuscript repository.
PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
REPO_ROOT = SCRIPTS_DIR.parent  # the manuscript repository when mounted there
CONFIG_DIR = SCRIPTS_DIR / "config"

DATA_DIR = SCRIPTS_DIR / "data"
RAW_DIR = DATA_DIR / "raw"          # cached per-source API pulls (gitignored)
PROCESSED_DIR = DATA_DIR / "processed"  # tidy CSVs consumed by figures (committed)

TOOLS_YML = CONFIG_DIR / "tools.yml"
DL_LEXICON_YML = CONFIG_DIR / "dl_lexicon.yml"
#DL_LEXICON_YML = CONFIG_DIR / "dl_ij_lexicon.yml"
FIGURES_DIR = REPO_ROOT / "MANUSCRIPT" / "FIGURES"


def ensure_dirs() -> None:
    for d in (RAW_DIR, PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)
