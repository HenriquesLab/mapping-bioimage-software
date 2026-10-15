"""PyPI source: recent download volume per tool (snapshot signal).

Uses the pypistats.org API `/recent` endpoint, which exposes last-day, last-week
and last-month download totals per package. This is a recent-adoption snapshot,
not a multi-year trend: PyPI does not publish long-run historical download
counts for free (that needs the public BigQuery `pypi` dataset). We therefore
treat PyPI as a convergent, present-day signal alongside GitHub, and keep the
yearly trends to OpenAlex + Europe PMC.

Run standalone:
    python -m census.sources.pypi --tool napari
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from census._http import get_json  # noqa: E402
from census._registry import Tool, load_registry  # noqa: E402

API = "https://pypistats.org/api/packages/"
SOURCE = "pypi"


def recent_downloads(package: str) -> int:
    """Downloads over the last 30 days for a package (0 if unavailable)."""
    url = f"{API}{package}/recent"
    try:
        data = get_json(SOURCE, url)
    except RuntimeError:
        return 0
    return int((data.get("data") or {}).get("last_month", 0))


def collect_snapshot(reg) -> list[dict]:
    as_of = dt.date.today().isoformat()
    rows: list[dict] = []
    for tool in reg.tools:
        if not tool.pypi:
            continue
        total = sum(recent_downloads(pkg) for pkg in tool.pypi)
        rows.append(
            {
                "source": SOURCE,
                "tool_id": tool.id,
                "downloads_30d": total,
                "packages": ";".join(tool.pypi),
                "as_of": as_of,
            }
        )
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="single tool id (default: all)")
    args = ap.parse_args()
    reg = load_registry()
    tools = [reg.by_id(args.tool)] if args.tool else reg.tools
    for t in tools:
        for pkg in t.pypi:
            print(f"{t.id:15} {pkg:15} last_30_days={recent_downloads(pkg):,}")
