"""Build historical Europe PMC counts for the 1995-2009 figure extension.

The configured analysis remains 2010-2025. This module adds package and corpus
hit counts for the years before that window, using the same cached hit-count API.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR
from census._registry import Registry, load_registry
from census.sources import europepmc

HISTORY_START_YEAR = 1995


def historical_years(registry: Registry) -> list[int]:
    """Return the years before the configured analysis window, starting in 1995."""
    return list(range(HISTORY_START_YEAR, registry.year_start))


def build_historical_counts(
    registry: Registry | None = None,
    output_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write identifier-free yearly package mentions and microscopy-corpus counts."""
    registry = registry or load_registry()
    years = historical_years(registry)
    if not years:
        raise ValueError("The configured analysis window leaves no years from 1995 to collect")

    mention_rows: list[dict] = []
    for tool in registry.tools:
        mention_rows.extend(
            {"tool_id": tool.id, "year": year, "count": count}
            for year, count in europepmc.yearly_counts(tool, registry, years=years).items()
        )
    mentions = pd.DataFrame(mention_rows, columns=["tool_id", "year", "count"])

    corpus_counts = europepmc.yearly_query_counts(registry.context_query, years)
    corpus = pd.DataFrame(
        [{"year": year, "microscopy_papers": corpus_counts[year]} for year in years],
        columns=["year", "microscopy_papers"],
    )

    output_dir = output_dir or PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    mentions.to_csv(output_dir / "historical_mentions_yearly.csv", index=False)
    corpus.to_csv(output_dir / "historical_corpus_yearly.csv", index=False)
    return mentions, corpus


def main() -> None:
    mentions, corpus = build_historical_counts()
    print(
        f"Built {len(mentions)} package-year counts for "
        f"{mentions['year'].min()}-{mentions['year'].max()} and "
        f"{len(corpus)} yearly corpus counts."
    )


if __name__ == "__main__":
    main()
