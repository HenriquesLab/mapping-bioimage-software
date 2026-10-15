"""Europe PMC source: full-text-aware yearly mention counts per tool.

Europe PMC (https://europepmc.org) searches the full text of the open-access
subset in addition to titles/abstracts for all records. Tools are usually named
in the Methods section, so this is the strongest "actually used" literature
signal and the direct answer to OpenAlex's abstract-only blind spot.

One lightweight request per (tool, year) returns just the hitCount.

Run standalone:
    python -m census.sources.europepmc --tool cellpose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from census._http import get_json  # noqa: E402
from census._registry import Tool, build_boolean_query, load_registry  # noqa: E402

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
SOURCE = "europepmc"
RA_NON_REVIEW_FILTER = "(((SRC:MED OR SRC:PMC OR SRC:AGR OR SRC:CBA) NOT (PUB_TYPE:'Review')))"


def _hit_count(query: str) -> int:
    params = {"query": query, "format": "json", "pageSize": 1, "resultType": "idlist"}
    data = get_json(SOURCE, API, params)
    if "hitCount" not in data:
        data = get_json(SOURCE, API, params, use_cache=False)
    if "hitCount" not in data:
        raise RuntimeError(f"Europe PMC response missing hitCount for query: {query}")
    return int(data.get("hitCount", 0))


def yearly_counts(tool: Tool, reg) -> dict[int, int]:
    base = build_boolean_query(tool, reg.context_query)
    return yearly_query_counts(base, reg.years)


from concurrent.futures import ThreadPoolExecutor, as_completed

def yearly_query_counts(query: str, years: list[int]) -> dict[int, int]:
    """Return yearly hit counts for a prebuilt Europe PMC query."""
    counts: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_hit_count, f"{query} AND PUB_YEAR:{y} AND {RA_NON_REVIEW_FILTER}"): y for y in years}
        for fut in as_completed(futures):
            counts[futures[fut]] = fut.result()
    return {y: counts[y] for y in sorted(counts)}


def sample_works(tool: Tool, reg, year: int, max_records: int = 200) -> list[dict]:
    """Capped sample of works with abstracts for one tool-year (for DL split).

    Uses resultType=core to obtain abstractText. Europe PMC has no per-request
    credit budget, so this is the budget-free sampling path for census.build.classify_dl.
    """
    base = build_boolean_query(tool, reg.context_query)
    query = f"{base} AND PUB_YEAR:{year} AND {RA_NON_REVIEW_FILTER}"
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
