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
CORPUS_COLUMNS = ["tool_id", "year", "epmc_id", "population", "n_sampled", "venue", "title", "abstract"]
ID_COLUMNS = CORPUS_COLUMNS[:6]


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('--replicates', action='store_true', help='write new disjoint replicate outputs only')
    ap.add_argument('--tool', action='append', dest='tool_ids', metavar='ID',
                    help='rebuild selected package samples and merge them into the existing corpus')
    args = ap.parse_args()
    if args.replicates and args.tool_ids:
        ap.error('--replicates cannot be combined with --tool')
    if args.replicates:
        from census.validation.replicates import abstracts
        abstracts(years=list(YEARS))
        return
    ensure_dirs()
    reg = load_registry()
    tool_ids = set(args.tool_ids or [])
    known_ids = {tool.id for tool in reg.tools}
    unknown_ids = sorted(tool_ids - known_ids)
    if unknown_ids:
        ap.error(f'unknown tool ID(s): {", ".join(unknown_ids)}')

    corpus_path = PROCESSED_DIR / "random_sample_2021_2025.csv.gz"
    previous = None
    if tool_ids:
        if not corpus_path.exists():
            ap.error(f'--tool requires an existing {corpus_path.name}; run without --tool first')
        previous = pd.read_csv(corpus_path, dtype={"epmc_id": str})
        missing_columns = set(CORPUS_COLUMNS) - set(previous.columns)
        if missing_columns:
            ap.error(f'existing corpus is missing columns: {", ".join(sorted(missing_columns))}')
        previous = previous.loc[~previous["tool_id"].isin(tool_ids), CORPUS_COLUMNS].copy()

    caps = {t["id"]: int(t.get("dl_sample_cap", DEFAULT_CAP))
            for t in yaml.safe_load(TOOLS_YML.read_text())["tools"]}
    selected_tools = [tool for tool in reg.tools if not tool_ids or tool.id in tool_ids]
    jobs = [(tool, year) for tool in selected_tools for year in YEARS]

    def one(ty):
        tool, year = ty
        works, population = europepmc.random_sample_works(tool, reg, year, caps.get(tool.id, DEFAULT_CAP))
        return [{**work, "population": population, "n_sampled": len(works)} for work in works]

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [row for chunk in ex.map(one, jobs) for row in chunk]
    df = pd.DataFrame(rows, columns=CORPUS_COLUMNS)
    if previous is not None:
        df = pd.concat([previous, df], ignore_index=True)
    df["epmc_id"] = df["epmc_id"].astype(str)
    tool_order = {tool.id: i for i, tool in enumerate(reg.tools)}
    df["_tool_order"] = df["tool_id"].map(tool_order)
    if df["_tool_order"].isna().any():
        raise ValueError("sample contains unregistered tool IDs")
    df = df.sort_values(["_tool_order", "year"], kind="stable").drop(columns="_tool_order").reset_index(drop=True)
    if df.duplicated(["tool_id", "year", "epmc_id"]).any():
        raise ValueError("sample contains duplicate package-year identifiers")

    df.to_csv(corpus_path, index=False)
    df[ID_COLUMNS].to_csv(PROCESSED_DIR / "random_sample_2021_2025_ids.csv", index=False)
    print(df.groupby("tool_id").size().to_string())


if __name__ == "__main__":
    main()
