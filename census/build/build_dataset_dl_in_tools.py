"""Build yearly Europe PMC counts for deep-learning use within core packages.

This is a parallel builder for explicit DL-within-package search queries. It
reads config/DL_in_tools.yml, combines each package's aliases and context with
the configured deep-learning lexicon include terms, and counts yearly Europe
PMC research-article hits through sources/europepmc_RA.py. Package aliases are
searched without a field scope; only the deep-learning clause is restricted to
TITLE and ABSTRACT. The lexicon is config/dl_in_tools_lexicon.yml.

Output:
  data/processed/dl_in_tools_yearly.csv
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from census._paths import CONFIG_DIR, PROCESSED_DIR, ensure_dirs  # noqa: E402
from census._registry import load_registry, query_term
from census.sources import europepmc_RA  # noqa: E402

CONFIG_YML = CONFIG_DIR / "DL_in_tools.yml"
OUTPUT_CSV = PROCESSED_DIR / "dl_in_tools_yearly.csv"
SOURCE_LABEL = "europepmc_RA"
QUERY_KIND = "dl_in_tool"
BASE_KIND = "tool_base"


@dataclass
class DLInTool:
    id: str
    name: str
    aliases: list[str]
    needs_context: bool
    dl_lexicon: str


@dataclass
class DLInToolsConfig:
    years: list[int]
    context_query: str
    default_dl_lexicon: str
    tools: list[DLInTool]


def _term_text(item: str | dict) -> str:
    if isinstance(item, dict):
        return str(item["term"])
    return str(item)


_REG_TOOL = load_registry().tools[0]  # carries the registry-wide exact list and wildcard setting


def _quote(term: str) -> str:
    escaped = term.replace('"', r"\"")
    return f'"{escaped}"'


def _title_or_abstract_term(term: str) -> str:
    quoted = _quote(term)
    return f"(TITLE:{quoted} OR ABSTRACT:{quoted})"


def load_config(path: Path = CONFIG_YML) -> DLInToolsConfig:
    raw = yaml.safe_load(path.read_text())
    settings = raw["settings"]
    default_lexicon = settings["default_dl_lexicon"]
    tools = [
        DLInTool(
            id=entry["id"],
            name=entry["name"],
            aliases=list(entry["aliases"]),
            needs_context=bool(
                entry.get("context_query", entry.get("needs_context", False))
            ),
            dl_lexicon=entry.get("dl_lexicon", default_lexicon),
        )
        for entry in raw["tools"]
    ]
    return DLInToolsConfig(
        years=list(range(int(settings["year_start"]), int(settings["year_end"]) + 1)),
        context_query=" ".join(settings["context_query"].split()),
        default_dl_lexicon=default_lexicon,
        tools=tools,
    )


def load_lexicon_terms(filename: str) -> tuple[list[str], list[str], int]:
    path = CONFIG_DIR / filename
    raw = yaml.safe_load(path.read_text())
    include_terms = [_term_text(item) for item in raw.get("include", [])]
    exclude_terms = [_term_text(item) for item in raw.get("exclude_guard", [])]
    return include_terms, exclude_terms, int(raw.get("version", 0))


def build_tool_query(
    tool: DLInTool,
    context_query: str,
    dl_terms: list[str],
    exclude_terms: list[str] | None = None,
) -> str:
    alias_clause = " OR ".join(query_term(alias, _REG_TOOL.default_exact(alias)) for alias in tool.aliases)
    tool_clause = f"({alias_clause})"
    if tool.needs_context:
        tool_clause = f"{tool_clause} AND ({context_query})"
    if not dl_terms:
        return f"({tool_clause})"
    dl_clause = " OR ".join(_title_or_abstract_term(term) for term in dl_terms)
    query = f"({tool_clause}) AND ({dl_clause})"
    if exclude_terms:
        exclude_clause = " OR ".join(
            _title_or_abstract_term(term) for term in exclude_terms
        )
        query = f"{query} NOT ({exclude_clause})"
    return query


def collect_yearly(config: DLInToolsConfig) -> list[dict]:
    rows: list[dict] = []
    lexicon_cache: dict[str, tuple[list[str], list[str], int]] = {}
    for tool in config.tools:
        if tool.dl_lexicon not in lexicon_cache:
            lexicon_cache[tool.dl_lexicon] = load_lexicon_terms(tool.dl_lexicon)
        terms, exclude_terms, version = lexicon_cache[tool.dl_lexicon]
        query = build_tool_query(tool, config.context_query, terms, exclude_terms)
        # The matching denominator: the same package clause under the same
        # research-article filter, without the deep-learning terms, so the
        # ratio compares like with like.
        base = build_tool_query(tool, config.context_query, [], None)
        for kind, q in ((QUERY_KIND, query), (BASE_KIND, base)):
            counts = europepmc_RA.yearly_query_counts(q, config.years)
            for year, count in counts.items():
                rows.append(
                    {
                        "source": SOURCE_LABEL,
                        "tool_id": tool.id,
                        "year": year,
                        "count": count,
                        "query_kind": kind,
                        "lexicon_version": version,
                    }
                )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=CONFIG_YML)
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV)
    args = ap.parse_args()

    ensure_dirs()
    config = load_config(args.config)
    df = pd.DataFrame(collect_yearly(config))
    df.to_csv(args.output, index=False)
    print(f"{args.output.name}: {len(df)} rows -> {args.output}")


if __name__ == "__main__":
    main()
