"""Blot-mention sensitivity for all registry tools, 2010–2025.

Run with the pipeline's Python environment. Writes
 data/processed/blot_sensitivity_yearly.csv, one row per scope/year/tool.
The full_text scope uses the registry query unchanged. The methods scope
(2025 only) requires tool, microscopy and blot terms in METHODS sections.
All requests use Europe PMC's _hit_count -> _http.get_json disk cache.

Reach without blots retains the original microscopy denominator, matching
the historical sensitivity. A separate column uses the blot-free denominator.
Analysis shares sum tool-paper matches, not deduplicated papers, and exclude
acquisition suites and tools marked in_aggregate: false (MATLAB and Jupyter notebooks).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from census._paths import PROCESSED_DIR
from census._registry import build_boolean_query, load_registry
from census.sources.europepmc import _hit_count

YEARS = range(2010, 2026)
BLOT_TERMS = (
    'western blot', 'immunoblot', 'blotting',
    'densitometry', 'densitometric', 'gel quantification',
)
METHODS_MICRO = '(METHODS:"microscopy" OR METHODS:"microscope") AND HAS_FT:Y'


def build_queries(reg) -> dict:
    """Count all and blot-positive subsets of each tool and its corpus."""
    jobs = {}
    for scope, years in (('full_text', YEARS), ('methods', [2025])):
        prefix = 'METHODS:' if scope == 'methods' else ''
        blot = '(' + ' OR '.join(f'{prefix}"{term}"' for term in BLOT_TERMS) + ')'
        context = METHODS_MICRO if scope == 'methods' else reg.context_query
        for year in years:
            bases = {'corpus': f'({context})'}
            for tool in reg.tools:
                if scope == 'methods':
                    aliases = '(' + ' OR '.join(tool.terms('METHODS:')) + ')'
                    bases[tool.id] = f'{aliases} AND ({context})'
                else:
                    bases[tool.id] = build_boolean_query(tool, context)
            for tool_id, base in bases.items():
                query = f'{base} AND PUB_YEAR:{year}'
                jobs[(scope, year, tool_id, 'all')] = query
                jobs[(scope, year, tool_id, 'with_blot')] = f'{query} AND {blot}'
    return jobs


def summarize(reg, counts: dict) -> pd.DataFrame:
    """Subtract blot subsets from every tool before forming analysis shares."""
    reg.by_id('imagej')
    analysis = [t.id for t in reg.tools if t.in_aggregate and t.category != 'acquisition-suite']
    if 'imagej' not in analysis:
        raise ValueError('ImageJ must belong to the analysis aggregate')
    rows = []
    for scope, years in (('full_text', YEARS), ('methods', [2025])):
        for year in years:
            pairs = {tid: (counts[(scope, year, tid, 'all')],
                           counts[(scope, year, tid, 'with_blot')])
                     for tid in ['corpus'] + [t.id for t in reg.tools]}
            corpus, corpus_blot = pairs['corpus']
            for tid, (all_count, blot_count) in pairs.items():
                if not 0 <= blot_count <= all_count <= corpus:
                    raise ValueError(f'{scope}/{year}/{tid}: invalid all/blot counts {all_count}/{blot_count}')
                if blot_count > corpus_blot or all_count - blot_count > corpus - corpus_blot:
                    raise ValueError(f'{scope}/{year}/{tid}: tool subset exceeds corresponding corpus')
            ij, ij_blot = pairs['imagej']
            ij_without = ij - ij_blot
            total = sum(pairs[tid][0] for tid in analysis)
            without = sum(pairs[tid][0] - pairs[tid][1] for tid in analysis)
            metrics = {
                'microscopy_papers': corpus,
                'microscopy_with_blot': corpus_blot,
                'microscopy_without_blot': corpus - corpus_blot,
                'analysis_mentions_all': total,
                'analysis_mentions_with_blot': total - without,
                'analysis_mentions_without_blot': without,
                'imagej_blot_pct': 100 * ij_blot / ij if ij else float('nan'),
                'imagej_reach_all_pct': 100 * ij / corpus if corpus else float('nan'),
                'imagej_reach_without_blot_pct': 100 * ij_without / corpus if corpus else float('nan'),
                'imagej_reach_in_blot_free_corpus_pct':
                    100 * ij_without / (corpus - corpus_blot) if corpus != corpus_blot else float('nan'),
                'imagej_share_analysis_all_pct': 100 * ij / total if total else float('nan'),
                'imagej_share_analysis_without_blot_pct': 100 * ij_without / without if without else float('nan'),
            }
            for tool in reg.tools:
                all_count, blot_count = pairs[tool.id]
                rows.append({
                    'scope': scope, 'year': year, 'tool_id': tool.id, 'tool_name': tool.name,
                    'in_analysis_aggregate': tool.id in analysis,
                    'papers_all': all_count, 'papers_with_blot': blot_count,
                    'papers_without_blot': all_count - blot_count, **metrics,
                })
    return pd.DataFrame(rows)


def main() -> None:
    reg = load_registry()
    jobs = build_queries(reg)
    print(f'Counting {len(jobs)} cached Europe PMC queries for {len(reg.tools)} tools', flush=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        counts = dict(zip(jobs, ex.map(_hit_count, jobs.values())))
    frame = summarize(reg, counts)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output = PROCESSED_DIR / 'blot_sensitivity_yearly.csv'
    frame.to_csv(output, index=False)
    columns = ['scope', 'year', 'papers_all', 'papers_with_blot', 'papers_without_blot',
               'microscopy_papers', 'imagej_reach_all_pct', 'imagej_reach_without_blot_pct',
               'imagej_share_analysis_without_blot_pct']
    selected = frame[(frame.tool_id == 'imagej') & frame.year.isin([2010, 2020, 2025])]
    print(selected[columns].to_string(index=False, float_format=lambda v: f'{v:.3f}'))
    print(f'Wrote {len(frame)} rows to {output}', flush=True)


if __name__ == '__main__':
    main()
