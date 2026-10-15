"""Build yearly Europe PMC counts for strict DL-within-package matching.

Query requirements per paper:
1. any configured package alias (full text),
2. context_query term(s) when needs_context is true for the tool,
3. either any configured full_text_alias for that tool, or none of the
   configured full_text_exclude_terms for that tool. Optional title_aliases are
   searched only in TITLE. Optional
   abstract_methods_results_aliases are searched only in ABSTRACT, METHODS or
   RESULTS. Optional introduction_exclude_terms are applied as INTRO-scoped
   exclusions. For Jupyter, use the DL-in-tools query shape and apply full-text
   excludes unless an override full-text term is present,
4. any term from config/dl_within_tools_lexicon.yml in TITLE or ABSTRACT.
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

CONFIG_YML = CONFIG_DIR / "DL_within_tools.yml"
DL_LEXICON_YML = CONFIG_DIR / "dl_within_tools_lexicon.yml"
OUTPUT_CSV = PROCESSED_DIR / "dl_within_tools_yearly.csv"
SOURCE_LABEL = "europepmc_RA"
QUERY_KIND = "dl_within_tool_context_fulltext_title_abstract_dl_within_lexicon"


@dataclass
class DLWithinTool:
    id: str
    name: str
    aliases: list[str]
    full_text_aliases: list[str]
    title_aliases: list[str]
    abstract_methods_results_aliases: list[str]
    full_text_exclude_terms: list[str]
    introduction_exclude_terms: list[str]
    full_text_override_terms: list[str]
    needs_context: bool


@dataclass
class DLWithinToolsConfig:
    years: list[int]
    context_query: str
    tools: list[DLWithinTool]


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


def load_config(path: Path = CONFIG_YML) -> DLWithinToolsConfig:
    raw = yaml.safe_load(path.read_text())
    settings = raw["settings"]
    tools = [
        DLWithinTool(
            id=entry["id"],
            name=entry["name"],
            aliases=list(entry["aliases"]),
            full_text_aliases=list(entry.get("full_text_aliases", [])),
            title_aliases=list(entry.get("title_aliases", entry.get("abstract_aliases", []))),
            abstract_methods_results_aliases=list(
                entry.get(
                    "abstract_methods_results_aliases",
                    entry.get("methods_results_aliases", []),
                )
            ),
            full_text_exclude_terms=list(entry.get("full_text_exclude_terms", [])),
            introduction_exclude_terms=list(
                entry.get("introduction_exclude_terms", [])
            ),
            full_text_override_terms=list(entry.get("full_text_override_terms", [])),
            needs_context=bool(
                entry.get("context_query", entry.get("needs_context", False))
            ),
        )
        for entry in raw["tools"]
    ]
    return DLWithinToolsConfig(
        years=list(range(int(settings["year_start"]), int(settings["year_end"]) + 1)),
        context_query=" ".join(settings["context_query"].split()),
        tools=tools,
    )


def load_lexicon_terms(path: Path = DL_LEXICON_YML) -> tuple[list[str], list[str], int]:
    raw = yaml.safe_load(path.read_text())
    include_terms = [_term_text(item) for item in raw.get("include", [])]
    exclude_terms = [_term_text(item) for item in raw.get("exclude_guard", [])]
    return include_terms, exclude_terms, int(raw.get("version", 0))


def build_tool_query(
    tool: DLWithinTool,
    context_query: str,
    title_abstract_dl_terms: list[str],
    exclude_terms: list[str] | None = None,
) -> str | None:
    if (
        tool.id != "jupyter"
        and not tool.full_text_aliases
        and not tool.title_aliases
        and not tool.abstract_methods_results_aliases
        and not tool.full_text_exclude_terms
        and not tool.introduction_exclude_terms
    ):
        return None

    aliases = sorted(tool.aliases, key=len, reverse=True)
    alias_clause = " OR ".join(query_term(alias, _REG_TOOL.default_exact(alias)) for alias in aliases)
    dl_clause = " OR ".join(_title_or_abstract_term(term) for term in title_abstract_dl_terms)
    clauses = [f"({alias_clause})"]
    if tool.needs_context:
        clauses.append(f"({context_query})")
    include_alias_clauses = []
    if tool.id != "jupyter" and tool.full_text_aliases:
        include_alias_clauses.append(
            " OR ".join(_quote(alias) for alias in tool.full_text_aliases)
        )
    if tool.id != "jupyter" and tool.title_aliases:
        title_clause = " OR ".join(
            f"TITLE:{_quote(alias)}" for alias in tool.title_aliases
        )
        include_alias_clauses.append(title_clause)
    if tool.id != "jupyter" and tool.abstract_methods_results_aliases:
        section_clause = " OR ".join(
            f"ABSTRACT:{_quote(alias)} OR METHODS:{_quote(alias)} OR RESULTS:{_quote(alias)}"
            for alias in tool.abstract_methods_results_aliases
        )
        include_alias_clauses.append(section_clause)
    if include_alias_clauses:
        clauses.append(f"({' OR '.join(f'({clause})' for clause in include_alias_clauses)})")
    clauses.append(f"({dl_clause})")
    query = " AND ".join(clauses)
    if tool.full_text_exclude_terms:
        full_text_exclude_clause = " OR ".join(
            _quote(term) for term in tool.full_text_exclude_terms
        )
        if tool.id == "jupyter" and tool.full_text_override_terms:
            override_clause = " OR ".join(
                _quote(term) for term in tool.full_text_override_terms
            )
            query = (
                f"{query} NOT (({full_text_exclude_clause}) "
                f"AND NOT ({override_clause}))"
            )
        else:
            query = f"{query} NOT ({full_text_exclude_clause})"
    if tool.introduction_exclude_terms:
        intro_exclude_clause = " OR ".join(
            f"INTRO:{_quote(term)}" for term in tool.introduction_exclude_terms
        )
        query = f"{query} NOT ({intro_exclude_clause})"
    if exclude_terms:
        exclude_clause = " OR ".join(_title_or_abstract_term(term) for term in exclude_terms)
        query = f"{query} NOT ({exclude_clause})"
    return query


def build_year_query(base_query: str, year: int) -> str:
    return f"{base_query} AND PUB_YEAR:{year} AND {europepmc_RA.RA_NON_REVIEW_FILTER}"


def collect_yearly(config: DLWithinToolsConfig) -> list[dict]:
    rows: list[dict] = []
    dl_terms, exclude_terms, version = load_lexicon_terms(DL_LEXICON_YML)
    for tool in config.tools:
        query = build_tool_query(tool, config.context_query, dl_terms, exclude_terms)
        if query is None:
            counts = {year: 0 for year in config.years}
        else:
            counts = europepmc_RA.yearly_query_counts(query, config.years)
        for year, count in counts.items():
            rows.append(
                {
                    "source": SOURCE_LABEL,
                    "tool_id": tool.id,
                    "year": year,
                    "count": count,
                    "query_kind": QUERY_KIND,
                    "lexicon_version": version,
                }
            )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=CONFIG_YML)
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV)
    ap.add_argument("--show-query-tool", help="tool id to print expected year query")
    ap.add_argument("--show-query-year", type=int, help="year for expected query print")
    args = ap.parse_args()

    ensure_dirs()
    config = load_config(args.config)
    df = pd.DataFrame(collect_yearly(config))
    df.to_csv(args.output, index=False)
    print(f"{args.output.name}: {len(df)} rows -> {args.output}")

    if args.show_query_tool and args.show_query_year is not None:
        dl_terms, exclude_terms, _ = load_lexicon_terms(DL_LEXICON_YML)
        tool = next((t for t in config.tools if t.id == args.show_query_tool), None)
        if tool is None:
            available = ", ".join(t.id for t in config.tools)
            print(f"Error: tool '{args.show_query_tool}' not found. Available: {available}")
            raise SystemExit(1)
        base = build_tool_query(tool, config.context_query, dl_terms, exclude_terms)
        if base is None:
            print(f"{tool.id}: no full_text_aliases or full_text_exclude_terms configured.")
        else:
            print(build_year_query(base, args.show_query_year))


if __name__ == "__main__":
    main()
