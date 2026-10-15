"""Robustness check: how many of each tool's matches fall in the Methods section.

Europe PMC indexes full-text sections separately (METHODS:, REF:), so a tool
named in Methods is more likely to have been run than one named only in the
introduction, discussion or references. Writes methods_section_2025.csv with,
for every tool, its 2025 matches, those naming it in Methods, and those naming
it in the reference list but not in Methods.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR, ensure_dirs  # noqa: E402
from census._registry import load_registry  # noqa: E402
from census.sources.europepmc import _hit_count  # noqa: E402

YEAR = 2025


def _field(tool, field: str) -> str:
    return "(" + " OR ".join(tool.terms(field)) + ")"


def main() -> None:
    ensure_dirs()
    reg = load_registry()
    ctx = f"({reg.context_query}) AND PUB_YEAR:{YEAR}"
    rows = []
    for t in reg.tools:
        anywhere, methods, refs = (_field(t, f) for f in ("", "METHODS:", "REF:"))
        n_all = _hit_count(f"{anywhere} AND {ctx}")
        n_methods = _hit_count(f"{methods} AND {ctx}")
        n_refs_only = _hit_count(f"{refs} AND NOT {methods} AND {ctx}")
        rows.append({"tool_id": t.id, "year": YEAR, "n_all": n_all, "n_methods": n_methods,
                     "share_methods": round(n_methods / n_all, 4) if n_all else None,
                     "n_refs_not_methods": n_refs_only})
    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED_DIR / "methods_section_2025.csv", index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
