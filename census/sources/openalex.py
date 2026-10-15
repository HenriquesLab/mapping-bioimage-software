"""OpenAlex source: yearly literature counts per package, plus an abstract sampler.

OpenAlex (https://openalex.org) indexes ~250M scholarly works with titles and
abstracts (as an inverted index). Two capabilities back this module:

  1. group_by=publication_year  -> one request yields the full yearly count
     curve for a package's boolean query (breadth signal).
  2. paged works with abstracts  -> a capped sample per package-year, in
     publication-date order.

yearly_counts is the active path for the annual counts in
census.build.build_dataset. sample_works is a separate access path that the
pipeline does not call: the deep-learning estimate samples through Europe PMC
(census.sources.europepmc.random_sample_works), because this module returns the
first records in publication-date order rather than a simple random sample.

Run standalone:
    python -m census.sources.openalex --tool napari
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from census._http import CONTACT_EMAIL, get_json  # noqa: E402
from census._registry import Tool, build_boolean_query, load_registry  # noqa: E402

API = "https://api.openalex.org/works"
SOURCE = "openalex"


def _base_filter(query: str, year_start: int, year_end: int) -> str:
    return (
        f"title_and_abstract.search:{query},"
        f"from_publication_date:{year_start}-01-01,"
        f"to_publication_date:{year_end}-12-31,"
        f"type:article"
    )


def yearly_counts(tool: Tool, reg) -> dict[int, int]:
    """Return {year: work_count} for a package across the configured range."""
    query = build_boolean_query(tool, reg.text_context, wildcard=False)
    params = {
        "filter": _base_filter(query, reg.year_start, reg.year_end),
        "group_by": "publication_year",
        "mailto": CONTACT_EMAIL,
    }
    data = get_json(SOURCE, API, params)
    counts = {y: 0 for y in reg.years}
    for grp in data.get("group_by", []):
        try:
            year = int(grp["key"])
        except (TypeError, ValueError):
            continue
        if year in counts:
            counts[year] = int(grp["count"])
    return counts


def _reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def sample_works(tool: Tool, reg, year: int, max_records: int = 200) -> list[dict]:
    """Capped sample of works (title, abstract, venue) for one package-year.

    Sorted by publication date and capped for tractability. Not used by the
    deep-learning estimate; see the module docstring.
    """
    query = build_boolean_query(tool, reg.text_context, wildcard=False)
    filt = (
        f"title_and_abstract.search:{query},"
        f"publication_year:{year},type:article"
    )
    out: list[dict] = []
    cursor = "*"
    while len(out) < max_records and cursor:
        params = {
            "filter": filt,
            "per_page": 200,
            "cursor": cursor,
            "select": "id,title,publication_year,abstract_inverted_index,primary_location",
            "sort": "publication_date:desc",
            "mailto": CONTACT_EMAIL,
        }
        data = get_json(SOURCE, API, params)
        for w in data.get("results", []):
            loc = w.get("primary_location") or {}
            src = (loc.get("source") or {}) if isinstance(loc, dict) else {}
            out.append(
                {
                    "tool_id": tool.id,
                    "year": year,
                    "openalex_id": w.get("id", ""),
                    "title": w.get("title") or "",
                    "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
                    "venue": (src.get("display_name") or "") if isinstance(src, dict) else "",
                }
            )
            if len(out) >= max_records:
                break
        cursor = (data.get("meta") or {}).get("next_cursor")
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
        total = sum(c.values())
        print(f"{t.id:15} total={total:8}  {dict(list(c.items())[-6:])}")
