"""Mentions against citations for the open-source packages, 2010-2025.

Europe PMC's default full-text search skips reference lists, and the REF field
searches only them. For each package and year, within the registry context
(microscopy, indexed full text), three hit counts give:
  named  - papers whose text names the package (registry aliases, trailing wildcard),
  cited  - papers that cite the package. For packages whose own papers Europe PMC
           indexes (config/package_papers.yml), a citation is a resolved citation
           link to one of those papers (CITES:<id>_<source>), method 'links'. For the
           others, a work with the package's name or a distinctive title phrase in
           its title anywhere in the reference list (REF field), method 'titles',
           which also admits plugin papers named after a host.
  both   - papers that do both.
named_not_cited and cited_not_named follow by subtraction. Commercial and
microscope-control software, which have no reference paper, are skipped.

Writes data/processed/mentions_citations_yearly.csv. All requests go through
the _http.get_json disk cache.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import yaml

from census._http import get_json
from census._paths import CONFIG_DIR, PROCESSED_DIR
from census._registry import build_boolean_query, load_registry
from census.sources.europepmc import API, SOURCE, _hit_count

YEARS = range(2010, 2026)
# Words or title phrases of each package's reference papers, searched in cited titles.
# A cited title that contains the word counts, including plugin papers named after a host.
REF_TERMS = {
    'imagej': ['ImageJ', 'Fiji'],
    'qupath': ['QuPath'],
    'cellprofiler': ['CellProfiler'],
    'ilastik': ['ilastik'],
    'napari': ['napari'],
    'icy': ['open bioimage informatics platform'],  # "Icy" alone is an ordinary word
    'knime': ['KNIME'],
    'cellpose': ['Cellpose'],
    'stardist': ['StarDist', 'star-convex'],        # the 2018 title omits the name
    'deepimagej': ['deepImageJ'],
    'zerocostdl4mic': ['ZeroCostDL4Mic', 'DL4MicEverywhere'],
    'jupyter': ['Jupyter'],
    'skimage': ['scikit-image'],
    'opencv': ['OpenCV'],
}


def ref_clause(terms):
    return '(' + ' OR '.join(f'REF:"{t}"' for t in terms) + ')'


def own_paper_records() -> dict[str, list[dict]]:
    """Indexed Europe PMC records of each package's own papers (config/package_papers.yml)."""
    out = {}
    for tool, dois in yaml.safe_load((CONFIG_DIR / 'package_papers.yml').read_text()).items():
        recs = []
        for doi in dois or []:
            d = get_json(SOURCE, API, {'query': f'DOI:"{doi}"', 'format': 'json', 'resultType': 'lite', 'pageSize': 5})
            recs += (d.get('resultList') or {}).get('result', [])
        out[tool] = recs
    return out


def own_papers() -> dict[str, list[str]]:
    """Record keys (id_source) of each package's indexed own papers."""
    return {t: sorted({f"{r['id']}_{r['source']}" for r in recs}) for t, recs in own_paper_records().items()}


def first_paper_year() -> dict[str, int]:
    """Publication year of each package's earliest indexed own paper."""
    return {t: min(int(r['pubYear']) for r in recs) for t, recs in own_paper_records().items() if recs}


def cite_clause(tool_id, own) -> tuple[str, str]:
    """(method, clause) for papers citing the package."""
    if own.get(tool_id):
        return 'links', '(' + ' OR '.join(f'CITES:{k}' for k in own[tool_id]) + ')'
    return 'titles', ref_clause(REF_TERMS[tool_id])


def build_queries(reg, own) -> dict:
    jobs = {}
    for tool in reg.tools:
        if tool.id not in REF_TERMS:
            continue
        named = build_boolean_query(tool, reg.context_query, wildcard=True)  # catches names fused with citation numbers
        _, cites = cite_clause(tool.id, own)
        for year in YEARS:
            jobs[(tool.id, year, 'named')] = f'{named} AND PUB_YEAR:{year}'
            jobs[(tool.id, year, 'cited')] = f'{cites} AND ({reg.context_query}) AND PUB_YEAR:{year}'
            jobs[(tool.id, year, 'both')] = f'{named} AND {cites} AND PUB_YEAR:{year}'
    return jobs


def summarize(counts: dict, own) -> pd.DataFrame:
    rows = []
    for tool_id in REF_TERMS:
        method = cite_clause(tool_id, own)[0]
        for year in YEARS:
            named, cited, both = (counts[(tool_id, year, k)] for k in ('named', 'cited', 'both'))
            if not both <= min(named, cited):
                raise ValueError(f'{tool_id}/{year}: both={both} exceeds named={named} or cited={cited}')
            rows.append(dict(tool_id=tool_id, method=method, year=year, named=named, cited=cited, both=both,
                             named_not_cited=named - both, cited_not_named=cited - both))
    return pd.DataFrame(rows)


def main() -> None:
    reg = load_registry()
    missing = set(REF_TERMS) - {t.id for t in reg.tools}
    if missing:
        raise ValueError(f'REF_TERMS names unknown packages: {sorted(missing)}')
    own = own_papers()
    jobs = build_queries(reg, own)
    with ThreadPoolExecutor(max_workers=6) as ex:
        counts = dict(zip(jobs, ex.map(_hit_count, jobs.values())))
    out = summarize(counts, own)
    path = PROCESSED_DIR / 'mentions_citations_yearly.csv'
    out.to_csv(path, index=False)
    recent = out[out.year >= 2021].groupby(['tool_id', 'method'])[['named', 'cited', 'both']].sum()
    recent['named_not_cited_pct'] = (100 * (1 - recent.both / recent.named)).round(0)
    recent['cited_not_named_pct'] = (100 * (1 - recent.both / recent.cited)).round(0)
    print(f'wrote {path} ({len(out)} rows); 2021-2025 totals:')
    print(recent.sort_values('named', ascending=False).to_string())


if __name__ == '__main__':
    main()
