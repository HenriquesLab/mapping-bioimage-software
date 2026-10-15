"""Host-platform co-mentions of the deep-learning tools (Figure 5).

For Cellpose and StarDist in each year from 2020, counts the microscopy papers
that name the tool, those that also name a host platform (ImageJ/Fiji, QuPath,
napari), and, among the ImageJ/Fiji co-mentions, those that also name (a) any
plugin or deepImageJ, and (b) the specific deep-learning plugin by phrase (for
example "StarDist plugin") or deepImageJ. All counts are complete Europe PMC hit counts (no sampling).
Co-mention shows that a paper names both tools; it does not show that one ran
inside the other, and a missing plugin term does not show that no plugin was
used, because authors rarely name the plugin they ran.

    python -m census.build.build_hosts
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR, ensure_dirs  # noqa: E402
from census._registry import build_boolean_query, load_registry  # noqa: E402
from census.sources.europepmc import _hit_count  # noqa: E402

DL_TOOLS = ["cellpose", "stardist"]
HOSTS = ["imagej", "qupath", "napari"]
ANY_PLUGIN = '("plugin" OR "plug-in" OR "deepImageJ")'
NAMED_PLUGIN = {
    "cellpose": '("Cellpose plugin" OR "Cellpose plug-in" OR "Cellpose wrapper" '
                'OR "Cellpose Fiji" OR "Cellpose ImageJ" OR "TrackMate-Cellpose" '
                'OR "BIOP" OR "deepImageJ")',
    "stardist": '("StarDist plugin" OR "StarDist plug-in" OR "StarDist Fiji plugin" '
                'OR "StarDist ImageJ plugin" OR "StarDist 2D plugin" '
                'OR "TrackMate-StarDist" OR "deepImageJ")',
}
YEARS = range(2020, 2026)


def main() -> None:
    ensure_dirs()
    reg = load_registry()
    rows = []
    for dl in DL_TOOLS:
        dl_q = build_boolean_query(reg.by_id(dl), reg.context_query)
        for year in YEARS:
            n_dl = _hit_count(f"{dl_q} AND PUB_YEAR:{year}")
            for host in HOSTS:
                host_q = build_boolean_query(reg.by_id(host), "")
                n_host = _hit_count(f"{dl_q} AND {host_q} AND PUB_YEAR:{year}")
                row = {"dl_tool": dl, "host": host, "year": year, "n_dl": n_dl,
                       "n_with_host": n_host,
                       "share_host": round(n_host / n_dl, 4) if n_dl else None}
                if host == "imagej":
                    for key, clause in (("any_plugin", ANY_PLUGIN), ("named_plugin", NAMED_PLUGIN[dl])):
                        n = _hit_count(f"{dl_q} AND {host_q} AND {clause} AND PUB_YEAR:{year}")
                        row[f"n_{key}"] = n
                        row[f"share_{key}_of_host"] = round(n / n_host, 4) if n_host else None
                rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED_DIR / "dl_host_comentions.csv", index=False)
    print(df[df.year == 2025].to_string(index=False))


if __name__ == "__main__":
    main()
