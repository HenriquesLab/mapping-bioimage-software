"""Load and validate the package registry (config/tools.yml)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from census._paths import TOOLS_YML

VALID_CATEGORIES = {"notebook", "general-platform", "dl-model", "commercial",
                    "figure-preparation", "library", "acquisition-suite"}
VALID_SCOPES = {"core", "counts"}


@dataclass
class Tool:
    id: str
    name: str
    category: str
    implies_dl: bool
    aliases: list[str]
    exclude_aliases: list[str] = field(default_factory=list)
    scope: str = "core"
    in_aggregate: bool = True
    github: list[str] = field(default_factory=list)
    pypi: list[str] = field(default_factory=list)
    imagesc_tags: list[str] = field(default_factory=list)
    homepage: str = ""
    caveat: str = ""
    exact_aliases: frozenset = frozenset()
    wildcard_default: bool = False

    def terms(self, field: str = "", wildcard: bool | None = None, longest_first: bool = False) -> list[str]:
        """Europe PMC terms for each alias (see query_term), in registry order so
        query strings, and their cached responses, match the original collection.
        wildcard=None follows the registry setting wildcard_aliases."""
        wildcard = self.wildcard_default if wildcard is None else wildcard
        aliases = sorted(self.aliases, key=len, reverse=True) if longest_first else self.aliases
        return [query_term(a, not wildcard or a in self.exact_aliases, field) for a in aliases]

    def default_exact(self, alias: str) -> bool:
        """Whether alias is searched exactly under the registry setting."""
        return not self.wildcard_default or alias in self.exact_aliases


@dataclass
class Registry:
    year_start: int
    year_end: int
    context_query: str
    tools: list[Tool]

    @property
    def years(self) -> list[int]:
        return list(range(self.year_start, self.year_end + 1))

    @property
    def text_context(self) -> str:
        """The context clause without Europe PMC's full-text filter, for
        sources such as OpenAlex that search titles and abstracts only."""
        return self.context_query.replace("AND HAS_FT:Y", "").strip().strip("()").strip()

    @property
    def core_tools(self) -> list[Tool]:
        """Packages whose papers are read for the deep-learning and research-area
        analyses; packages with scope 'counts' enter only the yearly counts."""
        return [t for t in self.tools if t.scope == "core"]

    def by_id(self, tool_id: str) -> Tool:
        for t in self.tools:
            if t.id == tool_id:
                return t
        raise KeyError(tool_id)


def load_registry() -> Registry:
    raw = yaml.safe_load(TOOLS_YML.read_text())
    s = raw["settings"]
    tools: list[Tool] = []
    seen: set[str] = set()
    for entry in raw["tools"]:
        if entry["category"] not in VALID_CATEGORIES:
            raise ValueError(f"{entry['id']}: bad category {entry['category']!r}")
        if entry.get("scope", "core") not in VALID_SCOPES:
            raise ValueError(f"{entry['id']}: bad scope {entry['scope']!r}")
        if entry["id"] in seen:
            raise ValueError(f"duplicate tool id {entry['id']!r}")
        seen.add(entry["id"])
        tools.append(
            Tool(
                id=entry["id"],
                name=entry["name"],
                category=entry["category"],
                implies_dl=bool(entry.get("implies_dl", False)),
                aliases=list(entry["aliases"]),
                exclude_aliases=list(entry.get("exclude_aliases", []) or []),
                scope=entry.get("scope", "core"),
                in_aggregate=bool(entry.get("in_aggregate", True)),
                github=list(entry.get("github", []) or []),
                pypi=list(entry.get("pypi", []) or []),
                imagesc_tags=list(entry.get("imagesc_tags", []) or []),
                homepage=entry.get("homepage", ""),
                caveat=(entry.get("caveat", "") or "").strip(),
            )
        )
    exact = frozenset(s.get("exact_aliases", []) or [])
    unknown = exact - {a for t in tools for a in t.aliases}
    if unknown:
        raise ValueError(f"exact_aliases not used by any tool: {sorted(unknown)}")
    for t in tools:
        t.exact_aliases = exact
        t.wildcard_default = bool(s.get("wildcard_aliases", False))
    context = " ".join(s["context_query"].split())
    return Registry(
        year_start=int(s["year_start"]),
        year_end=int(s["year_end"]),
        context_query=context,
        tools=tools,
    )


SINGLE_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def query_term(alias: str, exact: bool = False, field: str = "") -> str:
    """One Europe PMC term: a single word takes a trailing wildcard unless exact;
    phrases and words with punctuation are quoted. field is e.g. 'METHODS:'."""
    if not exact and SINGLE_WORD.fullmatch(alias):
        return f"{field}{alias}*"
    return f'{field}"{alias}"'


def alias_clause(tool: Tool, field: str = "", wildcard: bool | None = None) -> str:
    """The OR-ed alias terms in registry order, parenthesised for stable queries."""
    terms = tool.terms(field, wildcard)
    return f"({' OR '.join(terms)})"


def build_boolean_query(
    tool: Tool, context_query: str, wildcard: bool | None = None, field: str = ""
) -> str:
    """Compose an alias clause, exclusions and optional context.

    ``field`` prefixes both aliases and exclusions, for section-specific queries.
    wildcard=None follows the registry setting; False keeps every alias exact
    (OpenAlex search has no wildcards)."""
    clause = alias_clause(tool, field=field, wildcard=wildcard)
    if tool.exclude_aliases:
        excluded = " OR ".join(
            query_term(alias, exact=True, field=field) for alias in tool.exclude_aliases
        )
        clause = f"({clause} NOT ({excluded}))"
    if context_query:
        return f"{clause} AND ({context_query})"
    return clause


if __name__ == "__main__":
    reg = load_registry()
    print(f"{len(reg.tools)} tools, years {reg.year_start}-{reg.year_end}")
    for t in reg.tools:
        print(f"  [{t.category:16}] {t.id:15} {build_boolean_query(t, reg.context_query)[:80]}")
