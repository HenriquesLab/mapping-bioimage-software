"""Transparent deep-learning classifier for tool-mentioning papers.

A paper (title + abstract, optionally venue) is labelled deep-learning if it
matches any `include` term from config/dl_lexicon.yml and no `exclude_guard`
term. Matching is case-insensitive on word boundaries unless a term is marked
case-sensitive (CNN, GAN, VGG, CARE); multiword terms match as phrases. The lexicon is versioned and printed verbatim in the Supplementary, so
the labelling is fully auditable.

We do not label every matching work (millions for ImageJ). Instead we sample a
simple random sample of up to 200 works per tool-year from Europe PMC (which returns abstracts and
has no per-request credit budget), measure the DL fraction, and apply that
fraction to the yearly totals in census.build.build_dataset. This yields a per-year
DL / non-DL split that is reproducible and cheap.

Run standalone (estimate DL fraction from an OpenAlex sample):
    python -m census.build.classify_dl --tool cellpose --year 2024
"""

from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

import yaml

from census._paths import DL_LEXICON_YML  # noqa: E402
from census._registry import load_registry  # noqa: E402


@lru_cache(maxsize=1)
def _lexicon() -> tuple[list[re.Pattern], list[re.Pattern], int]:
    raw = yaml.safe_load(DL_LEXICON_YML.read_text())

    def _normalise_term(item: str | dict) -> tuple[str, bool]:
        if isinstance(item, str):
            return item, False
        if isinstance(item, dict) and "term" in item:
            return str(item["term"]), bool(item.get("case_sensitive", False))
        raise ValueError(f"invalid lexicon entry: {item!r}")

    def compile_terms(terms: list[str | dict]) -> list[re.Pattern]:
        pats = []
        for item in terms:
            term, case_sensitive = _normalise_term(item)
            esc = re.escape(term).replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]+")
            flags = 0 if case_sensitive else re.IGNORECASE
            pats.append(re.compile(rf"\b{esc}\b", flags))
        return pats

    inc = compile_terms(raw.get("include", []))
    exc = compile_terms(raw.get("exclude_guard", []))
    return inc, exc, int(raw.get("version", 0))


def lexicon_version() -> int:
    return _lexicon()[2]


def is_deep_learning(text: str) -> bool:
    """True if the text signals a deep-learning method."""
    inc, exc, _ = _lexicon()
    if not text:
        return False
    if any(p.search(text) for p in exc):
        return False
    return any(p.search(text) for p in inc)


def dl_fraction(works: list[dict]) -> tuple[int, int, float]:
    """Given sampled works with title+abstract, return (n_dl, n_total, frac)."""
    n_total = len(works)
    if n_total == 0:
        return 0, 0, 0.0
    n_dl = sum(
        1
        for w in works
        if is_deep_learning(f"{w.get('title', '')} {w.get('abstract', '')}")
    )
    return n_dl, n_total, n_dl / n_total


def estimate_tool_fractions(reg, sample_cap: int = 200) -> list[dict]:
    """DL fraction per tool-year, estimated from Europe PMC samples."""
    from census.sources import europepmc

    from concurrent.futures import ThreadPoolExecutor

    def one(tool, year, cap) -> dict:
        works, population = europepmc.random_sample_works(
            tool, reg, year, max_records=cap)
        n_dl, n_total, frac = dl_fraction(works)
        # A census has no sampling error for that tool-year, so its interval
        # collapses to the point; Wilson intervals apply to sampled tool-years.
        census = n_total >= population
        lo, hi = (frac, frac) if census else wilson(n_dl, n_total)
        return {
            "tool_id": tool.id,
            "year": year,
            "population": population,
            "n_sampled": n_total,
            "n_dl": n_dl,
            "dl_fraction": round(frac, 4),
            "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4),
            "sampling": "census" if census else "simple-random",
            "lexicon_version": lexicon_version(),
        }

    # Per-tool sample caps (tools.yml: dl_sample_cap). ImageJ/Fiji carries most
    # of the field-level weight, so a larger sample narrows the field interval.
    import yaml
    from census._paths import TOOLS_YML
    caps = {t["id"]: int(t.get("dl_sample_cap", sample_cap))
            for t in yaml.safe_load(TOOLS_YML.read_text())["tools"]}

    def one_capped(tool, year) -> dict:
        return one(tool, year, caps.get(tool.id, sample_cap))

    jobs = [(t, y) for t in reg.tools for y in reg.years]  # every tool's papers are read
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(lambda ty: one_capped(*ty), jobs))
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--cap", type=int, default=200)
    ap.add_argument('--replicates', action='store_true', help='write new disjoint replicate outputs only')
    args = ap.parse_args()
    if args.replicates:
        from census.validation.replicates import abstracts
        abstracts(tools=[args.tool], years=[args.year])
        sys.exit(0)
    reg = load_registry()
    from census.sources import europepmc

    # Same estimator as the pipeline: census up to CENSUS_MAX matches, simple
    # random sample above it. (sample_works takes the first records in
    # relevance order and biases the share upwards; do not use it here.)
    works, population = europepmc.random_sample_works(
        reg.by_id(args.tool), reg, args.year, max_records=args.cap)
    n_dl, n_total, frac = dl_fraction(works)
    if n_total >= population:
        how = "census, no sampling error"
    else:
        lo, hi = wilson(n_dl, n_total)
        how = f"95% CI {lo:.1%}-{hi:.1%}; random sample of {population}"
    print(f"{args.tool} {args.year}: DL {n_dl}/{n_total} = {frac:.1%} "
          f"({how}; lexicon v{lexicon_version()})")
