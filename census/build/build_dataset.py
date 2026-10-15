"""Collect every source and write the tidy CSVs the figures consume.

Outputs (scripts/data/processed/, committed to the repo so figures reproduce
without re-hitting any API):

  tools.csv               tool_id, name, category, implies_dl, homepage
  literature_yearly.csv   source, tool_id, year, count      (OpenAlex + EuropePMC)
  dl_estimates.csv        tool_id, year, n_sampled, n_dl, dl_fraction, lexicon_version
  dl_split_yearly.csv     tool_id, year, base_count, dl_fraction, count_dl, count_nondl
  dl_field_yearly.csv     year, count_dl, count_nondl, dl_share, dl_share_lo/hi (field-wide)
  corpus_yearly.csv       year, microscopy_papers                (reach denominator)
  adoption_snapshot.csv   tool_id, github_stars/forks, pypi_downloads_30d, imagesc_topics

Run:
    python -m census.build.build_dataset                 # full build (uses cached API pulls)
    python -m census.build.build_dataset --lit-only      # skip snapshots + DL sampling
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR, ensure_dirs  # noqa: E402
from census._registry import load_registry  # noqa: E402

# The DL split uses one consistent base source so shares are comparable.
# Europe PMC is chosen: full-text signal, and no OpenAlex credit budget.
DL_BASE_SOURCE = "europepmc"


def write_tools(reg) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "tool_id": t.id,
                "name": t.name,
                "category": t.category,
                "implies_dl": t.implies_dl,
                "in_aggregate": t.in_aggregate,
                "scope": t.scope,
                "homepage": t.homepage,
            }
            for t in reg.tools
        ]
    )
    df.to_csv(PROCESSED_DIR / "tools.csv", index=False)
    return df


def build_literature(reg) -> pd.DataFrame:
    from census.sources import europepmc, openalex

    rows = openalex.collect_yearly(reg) + europepmc.collect_yearly(reg)
    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED_DIR / "literature_yearly.csv", index=False)
    return df


def build_corpus(reg) -> pd.DataFrame:
    """Yearly count of every microscopy paper (the reach denominator)."""
    from census.sources import europepmc

    df = pd.DataFrame(europepmc.corpus_yearly(reg))
    df.to_csv(PROCESSED_DIR / "corpus_yearly.csv", index=False)
    return df


def build_dl(reg, lit: pd.DataFrame, sample_cap: int) -> None:
    from census.build import classify_dl

    est = pd.DataFrame(classify_dl.estimate_tool_fractions(reg, sample_cap))
    est.to_csv(PROCESSED_DIR / "dl_estimates.csv", index=False)

    base = lit[lit["source"] == DL_BASE_SOURCE][["tool_id", "year", "count"]]
    split = est.merge(base, on=["tool_id", "year"], how="left")
    split["base_count"] = split["count"].fillna(0).astype(int)
    split["count_dl"] = (split["base_count"] * split["dl_fraction"]).round().astype(int)
    split["count_nondl"] = split["base_count"] - split["count_dl"]
    split = split[
        ["tool_id", "year", "base_count", "dl_fraction", "count_dl", "count_nondl"]
    ]
    split.to_csv(PROCESSED_DIR / "dl_split_yearly.csv", index=False)

    # Field-wide aggregate excludes reference environments (MATLAB and Jupyter notebooks) so
    # they do not dominate the DL share; they remain in per-tool views.
    # The field series stays defined over the core tools, as the 13 core
    # analysis tools of Figure 5a, although every tool's papers are read.
    aggregate_ids = {t.id for t in reg.core_tools if t.in_aggregate}
    field_src = split[split["tool_id"].isin(aggregate_ids)]
    field = (
        field_src.groupby("year")[["count_dl", "count_nondl"]].sum().reset_index()
    )
    total = field["count_dl"] + field["count_nondl"]
    field["dl_share"] = (field["count_dl"] / total.replace(0, pd.NA)).fillna(0).round(4)

    # 95% interval for the field share. Each tool-year fraction is a simple
    # random sample; the field share is a count-weighted sum of them, so its
    # variance is the weighted sum of binomial variances with a finite-
    # population correction (zero where the tool-year was taken whole).
    v = est.merge(base, on=["tool_id", "year"], how="left")
    v = v[v["tool_id"].isin(aggregate_ids)].copy()
    n, N, p = v["n_sampled"], v["population"], v["dl_fraction"]
    fpc = ((N - n) / (N - 1).where(N > 1, 1)).clip(lower=0)
    v["var_count"] = (v["count"].fillna(0) ** 2) * p * (1 - p) / n.where(n > 0, 1) * fpc
    var = v.groupby("year")["var_count"].sum().reindex(field["year"]).to_numpy()
    se = (var ** 0.5) / total.replace(0, pd.NA).astype(float).to_numpy()
    field["dl_share_lo"] = (field["dl_share"] - 1.96 * se).clip(lower=0).round(4)
    field["dl_share_hi"] = (field["dl_share"] + 1.96 * se).round(4)
    field.to_csv(PROCESSED_DIR / "dl_field_yearly.csv", index=False)


def build_snapshots(reg) -> None:
    from census.sources import github, imagesc, pypi

    gh = {r["tool_id"]: r for r in github.collect_snapshot(reg)}
    pp = {r["tool_id"]: r for r in pypi.collect_snapshot(reg)}
    ic = {r["tool_id"]: r for r in imagesc.collect_snapshot(reg)}

    rows = []
    for t in reg.core_tools:
        g, p, i = gh.get(t.id, {}), pp.get(t.id, {}), ic.get(t.id, {})
        rows.append(
            {
                "tool_id": t.id,
                "category": t.category,
                "github_stars": g.get("stars", ""),
                "github_forks": g.get("forks", ""),
                "earliest_repo": g.get("earliest_repo", ""),
                "pypi_downloads_30d": p.get("downloads_30d", ""),
                "imagesc_topics": i.get("topics", ""),
            }
        )
    pd.DataFrame(rows).to_csv(PROCESSED_DIR / "adoption_snapshot.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lit-only", action="store_true", help="literature only")
    ap.add_argument("--sample-cap", type=int, default=200)
    args = ap.parse_args()

    ensure_dirs()
    reg = load_registry()
    write_tools(reg)
    lit = build_literature(reg)
    print(f"literature_yearly.csv: {len(lit)} rows")
    build_corpus(reg)
    print("corpus_yearly.csv written")
    if not args.lit_only:
        build_dl(reg, lit, args.sample_cap)
        print("dl_split_yearly.csv + dl_field_yearly.csv written")
        build_snapshots(reg)
        print("adoption_snapshot.csv written")
    print(f"processed CSVs -> {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
