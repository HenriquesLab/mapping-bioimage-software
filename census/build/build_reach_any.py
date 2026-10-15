"""Papers naming at least one package of a group, per year.

The per-package counts sum package-paper matches, so a paper naming three
packages counts three times. For grouped reach (Figure 4a) we count each paper
once: one Europe PMC query ORs the exact alias clauses of every package in the
group, with the census context and year.

Writes data/processed/reach_any_yearly.csv (year, group, papers).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from census._paths import PROCESSED_DIR
from census._registry import alias_clause, load_registry
from census.sources.europepmc import _hit_count


def groups(reg) -> dict[str, list]:
    tools = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")
    agg = tools[tools.in_aggregate]
    analysis = list(agg[agg.category != "acquisition-suite"].index)
    return {"analysis": analysis,
            "other_analysis": [t for t in analysis if t != "imagej"],
            "microscope_control": list(agg[agg.category == "acquisition-suite"].index)}


def main() -> None:
    reg = load_registry()
    by_id = {t.id: t for t in reg.tools}
    jobs = {}
    for g, ids in groups(reg).items():
        clause = " OR ".join(alias_clause(by_id[i]) for i in ids)
        for y in reg.years:
            jobs[(y, g)] = f"({clause}) AND ({reg.context_query}) AND PUB_YEAR:{y}"
    with ThreadPoolExecutor(max_workers=6) as ex:
        n = dict(zip(jobs, ex.map(_hit_count, jobs.values())))
    out = pd.DataFrame([{"year": y, "group": g, "papers": v} for (y, g), v in n.items()]).sort_values(["group", "year"])
    path = PROCESSED_DIR / "reach_any_yearly.csv"
    out.to_csv(path, index=False)
    corpus = pd.read_csv(PROCESSED_DIR / "corpus_yearly.csv").set_index("year").microscopy_papers
    out["pct"] = (100 * out.papers / out.year.map(corpus)).round(1)
    print(f"wrote {path}")
    print(out.pivot(index="year", columns="group", values="pct").to_string())


if __name__ == "__main__":
    main()
