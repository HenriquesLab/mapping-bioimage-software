"""image.sc source: community-support activity per tool (snapshot signal).

forum.image.sc is the central support forum for the bioimage-analysis
community, running Discourse. Its `/tags.json` endpoint lists every tag with a
topic count; we map each tool's registry tags to those counts as a
community-engagement snapshot.

Like GitHub/PyPI this is point-in-time, not a yearly trend.

IMPORTANT: the forum applies Discourse crawler protection and returns HTTP 403
("Crawler is not allowed!") to non-browser clients, including this script. The
module therefore FAILS SOFT: on a block it returns no rows and prints guidance.
To collect this signal, fetch `/tags.json` through the browser bridge (opencli)
and drop the JSON at scripts/data/raw/imagesc/tags.json; this module will then
read the cached file. Yearly trends never depend on this source.

Run standalone:
    python -m census.sources.imagesc
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from census._http import get_json  # noqa: E402
from census._registry import load_registry  # noqa: E402

TAGS_URL = "https://forum.image.sc/tags.json"
SOURCE = "imagesc"


def _load_cached_tags() -> dict | None:
    """Read a browser-collected tags.json if one was dropped in the cache."""
    from census._paths import RAW_DIR

    manual = RAW_DIR / "imagesc" / "tags.json"
    if manual.exists():
        import json

        return json.loads(manual.read_text())
    return None


def tag_counts() -> dict[str, int]:
    """Map tag slug -> topic count, or {} if the forum blocks the request."""
    data = _load_cached_tags()
    if data is None:
        try:
            data = get_json(SOURCE, TAGS_URL)
        except (RuntimeError, Exception):  # noqa: BLE001 - fail soft on 403
            print(
                "[imagesc] blocked by Discourse crawler protection; skipping.\n"
                "          Drop a browser-fetched tags.json at "
                "scripts/data/raw/imagesc/tags.json to enable this signal."
            )
            return {}
    counts: dict[str, int] = {}
    for t in data.get("tags", []):
        slug = t.get("name") or t.get("id")
        if slug is not None:
            counts[str(slug)] = int(t.get("count", 0))
    return counts


def collect_snapshot(reg) -> list[dict]:
    as_of = dt.date.today().isoformat()
    counts = tag_counts()
    rows: list[dict] = []
    for tool in reg.tools:
        if not tool.imagesc_tags:
            continue
        total = sum(counts.get(tag, 0) for tag in tool.imagesc_tags)
        rows.append(
            {
                "source": SOURCE,
                "tool_id": tool.id,
                "topics": total,
                "tags": ";".join(tool.imagesc_tags),
                "as_of": as_of,
            }
        )
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="single tool id (default: all)")
    args = ap.parse_args()
    reg = load_registry()
    counts = tag_counts()
    tools = [reg.by_id(args.tool)] if args.tool else reg.tools
    for t in tools:
        total = sum(counts.get(tag, 0) for tag in t.imagesc_tags)
        print(f"{t.id:15} topics={total:7}  tags={t.imagesc_tags}")
