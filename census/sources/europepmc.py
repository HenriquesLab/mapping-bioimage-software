"""Europe PMC source: full-text-aware yearly mention counts per package.

Europe PMC (https://europepmc.org) searches the full text of the open-access
subset in addition to titles/abstracts for all records. Packages are usually
named in the Methods section, so a full-text mention is the strongest available
literature signal and the direct answer to OpenAlex's abstract-only blind spot.
A mention shows that a paper names the package; it does not establish that the
authors ran it.

One lightweight request per (package, year) returns just the hitCount.

Run standalone:
    python -m census.sources.europepmc --tool cellpose
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from census._http import get_json  # noqa: E402
from census._registry import Tool, build_boolean_query, load_registry  # noqa: E402

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SOURCE = "europepmc"


def _hit_count(query: str) -> int:
    params = {"query": query, "format": "json", "pageSize": 1, "resultType": "idlist"}
    data = get_json(SOURCE, API, params)
    return int(data.get("hitCount", 0))


from concurrent.futures import ThreadPoolExecutor, as_completed

def yearly_counts(tool: Tool, reg) -> dict[int, int]:
    base = build_boolean_query(tool, reg.context_query)
    queries = [(y, f"{base} AND PUB_YEAR:{y}") for y in reg.years]
    counts: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_hit_count, q): y for y, q in queries}
        for fut in as_completed(futures):
            y = futures[fut]
            counts[y] = fut.result()
    return {y: counts[y] for y in sorted(counts)}


def sample_works(tool: Tool, reg, year: int, max_records: int = 200) -> list[dict]:
    """First max_records works in Europe PMC relevance order (NOT a random sample).

    Relevance ranking over-samples papers that feature a tool prominently, so
    estimates from this function fall as max_records rises. Kept only for ad
    hoc inspection; every estimate in the manuscript uses random_sample_works.

    Uses resultType=core to obtain abstractText. Europe PMC has no per-request
    credit budget, so this is the budget-free sampling path for census.build.classify_dl.
    """
    base = build_boolean_query(tool, reg.context_query)
    query = f"{base} AND PUB_YEAR:{year}"
    out: list[dict] = []
    cursor = "*"
    while len(out) < max_records and cursor:
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": 100,
            "cursorMark": cursor,
        }
        data = get_json(SOURCE, API, params)
        results = (data.get("resultList") or {}).get("result", [])
        if not results:
            break
        for r in results:
            journal = ((r.get("journalInfo") or {}).get("journal") or {})
            out.append(
                {
                    "tool_id": tool.id,
                    "year": year,
                    "epmc_id": r.get("id", ""),
                    "title": r.get("title") or "",
                    "abstract": r.get("abstractText") or "",
                    "venue": journal.get("title") or "",
                }
            )
            if len(out) >= max_records:
                break
        next_cursor = data.get("nextCursorMark")
        cursor = next_cursor if next_cursor and next_cursor != cursor else None
    return out


def _id_list(query: str) -> list[tuple[str, str]]:
    """Every (id, source) pair matching a query, paged with cursorMark."""
    ids: list[tuple[str, str]] = []
    cursor = "*"
    while cursor:
        params = {
            "query": query,
            "format": "json",
            "resultType": "idlist",
            "pageSize": 1000,
            "cursorMark": cursor,
        }
        data = get_json(SOURCE, API, params)
        results = (data.get("resultList") or {}).get("result", [])
        if not results:
            break
        ids.extend((r.get("id", ""), r.get("source", "")) for r in results)
        next_cursor = data.get("nextCursorMark")
        cursor = next_cursor if next_cursor and next_cursor != cursor else None
    return ids


def _fetch_records(pairs: list[tuple[str, str]], batch: int = 100) -> list[dict]:
    """Core records (title, abstract) for explicit (id, source) pairs."""
    out: list[dict] = []
    for i in range(0, len(pairs), batch):
        chunk = pairs[i : i + batch]
        query = " OR ".join(f"(EXT_ID:{pid} AND SRC:{src})" for pid, src in chunk)
        params = {"query": query, "format": "json", "resultType": "core",
                  "pageSize": batch}
        data = get_json(SOURCE, API, params)
        out.extend((data.get("resultList") or {}).get("result", []))
    return out


# Package-years with up to this many matches are read in full (a census), so
# their deep-learning share carries no sampling error. Larger package-years are
# sampled at the package's cap.
CENSUS_MAX = 2000


def random_sample_works(tool: Tool, reg, year: int, max_records: int = 200,
                        seed: int = 20260929,
                        census_max: int = CENSUS_MAX,
                        replicate: int | None = None) -> tuple[list[dict], int]:
    """Census or simple random sample of works with abstracts for one package-year.

    Draws from the complete id list of the tool-year, so every matching paper
    has the same chance of selection whatever Europe PMC's ranking. Tool-years
    with at most max(census_max, max_records) matches are taken whole; larger
    ones are sampled at max_records. Returns (works, population).
    """
    base = build_boolean_query(tool, reg.context_query)
    pairs = _id_list(f"{base} AND PUB_YEAR:{year}")
    population = len(pairs)
    rng = random.Random(f"{seed}-{tool.id}-{year}")
    whole = population <= max(census_max, max_records)
    chosen = pairs if whole else rng.sample(pairs, max_records)
    if replicate is not None:
        if replicate not in (1, 2, 3):
            raise ValueError('replicate must be 1, 2 or 3')
        from census.validation.replicates import draw_replicates, SEED
        base_seed = f'{SEED}-abstract-{tool.id}-{year}'
        if whole or population < 3 * max_records:
            parts = draw_replicates(pairs, max_records, seed=base_seed, census=True)
        else:
            parts = draw_replicates(pairs, max_records, first=chosen, seed=base_seed)
        chosen = parts[replicate - 1]
    works = []
    for r in _fetch_records(chosen):
        journal = ((r.get("journalInfo") or {}).get("journal") or {})
        works.append(
            {
                "tool_id": tool.id,
                "year": year,
                "epmc_id": r.get("id", ""),
                "title": r.get("title") or "",
                "abstract": r.get("abstractText") or "",
                "venue": journal.get("title") or "",
            }
        )
    return works, population


def corpus_yearly(reg) -> list[dict]:
    """Yearly count of every microscopy paper, the denominator for reach.

    Uses the same context clause the tool queries carry, so a tool's count
    divided by this count is the share of microscopy papers naming the package.
    """
    rows = []
    for year in reg.years:
        count = _hit_count(f"({reg.context_query}) AND PUB_YEAR:{year}")
        rows.append({"year": year, "microscopy_papers": count})
    return rows


def collect_yearly(reg) -> list[dict]:
    rows: list[dict] = []
    for tool in reg.tools:
        for year, count in yearly_counts(tool, reg).items():
            rows.append(
                {"source": SOURCE, "tool_id": tool.id, "year": year, "count": count}
            )
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="single tool id (default: all)")
    args = ap.parse_args()
    reg = load_registry()
    tools = [reg.by_id(args.tool)] if args.tool else reg.tools
    for t in tools:
        c = yearly_counts(t, reg)
        print(f"{t.id:15} total={sum(c.values()):8}  {dict(list(c.items())[-6:])}")
