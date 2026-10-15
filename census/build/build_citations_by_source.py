"""Naming and citing by source type: preprints against journal papers, 2021-2025.

For the packages whose own papers Europe PMC indexes (build_citations, method
'links'), the named / cited / both counts are split by source: preprints (SRC:PPR)
and all other records. Europe PMC has parsed the reference lists of far fewer
preprints than journal papers, and a paper without a parsed list can show no
citation link, so the counts are also restricted to records with a parsed
reference list (HAS_REFLIST:Y), the fair comparison.

Writes data/processed/citations_by_source_2021_2025.csv.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from census._paths import PROCESSED_DIR
from census._registry import build_boolean_query, load_registry
from census.build.build_citations import cite_clause, own_papers
from census.sources.europepmc import _hit_count

YEARS = 'PUB_YEAR:[2021 TO 2025]'
SOURCES = {'preprint': 'SRC:PPR', 'journal': '(NOT SRC:PPR)'}
REFLIST = {'all': '', 'parsed': ' AND HAS_REFLIST:Y'}


def main() -> None:
    reg = load_registry()
    own = own_papers()
    jobs = {}
    for g, gq in SOURCES.items():
        for rk, rq in REFLIST.items():
            base = f'{gq} AND {YEARS}{rq}'
            jobs[('microscopy', g, rk, 'named')] = f'({reg.context_query}) AND {base}'
            for t in reg.tools:
                if not own.get(t.id):
                    continue
                named = build_boolean_query(t, reg.context_query, wildcard=True)
                cites = cite_clause(t.id, own)[1]
                jobs[(t.id, g, rk, 'named')] = f'{named} AND {base}'
                jobs[(t.id, g, rk, 'both')] = f'{named} AND {cites} AND {base}'
                jobs[(t.id, g, rk, 'cited')] = f'{cites} AND ({reg.context_query}) AND {base}'
    with ThreadPoolExecutor(max_workers=6) as ex:
        c = dict(zip(jobs, ex.map(_hit_count, jobs.values())))
    rows = []
    for (t, g, rk, kind), v in c.items():
        rows.append(dict(tool_id=t, source=g, reference_list=rk, count=kind, n=v))
    out = pd.DataFrame(rows).pivot_table(index=['tool_id', 'source', 'reference_list'], columns='count', values='n').reset_index()
    out.columns.name = None
    path = PROCESSED_DIR / 'citations_by_source_2021_2025.csv'
    out.to_csv(path, index=False)
    p = out[out.reference_list == 'parsed'].copy()
    p = p[p.tool_id != 'microscopy']
    p['named_not_cited_pct'] = (100 * (p.named - p.both) / (p.named + p.cited - p.both)).round(1)
    print(f'wrote {path}')
    print(p.pivot(index='tool_id', columns='source', values=['named', 'named_not_cited_pct']).to_string())


if __name__ == '__main__':
    main()
