"""Exact against wildcard alias queries, for every registry package.

Europe PMC's index fuses a name with a citation number that follows it
("QuPath63"), so an exact query misses the paper; a trailing wildcard on
single-word aliases catches it (and versions such as Cellpose3). The census uses
exact names; this table reports what the wildcard changes in 2010, 2020 and 2025,
including ImageJ/Fiji's share of mentions of the 24 analysis packages.
Writes data/processed/wildcard_sensitivity.csv.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from census._paths import PROCESSED_DIR
from census._registry import build_boolean_query, load_registry
from census._http import get_json
from census.sources.europepmc import API, SOURCE

YEARS = (2010, 2020, 2025)


def _fresh_count(query: str) -> int:
    """Live hit count. Both forms are fetched on the same day: the census cache is
    dated 2 October 2026 and Europe PMC counts drift (ImageJ 2010, exact: 4,472
    then, 4,286 on 13 October)."""
    data = get_json(SOURCE, API, {'query': query, 'format': 'json', 'pageSize': 1, 'resultType': 'idlist'}, use_cache=False)
    return int(data.get('hitCount', 0))


def main() -> None:
    reg = load_registry()
    jobs = {(t.id, y, w): f'{build_boolean_query(t, reg.context_query, wildcard=w)} AND PUB_YEAR:{y}'
            for t in reg.tools for y in YEARS for w in (False, True)}
    with ThreadPoolExecutor(max_workers=6) as ex:
        counts = dict(zip(jobs, ex.map(_fresh_count, jobs.values())))
    rows = []
    for t in reg.tools:
        for y in YEARS:
            exact, wild = counts[(t.id, y, False)], counts[(t.id, y, True)]
            if wild < exact:
                raise ValueError(f'{t.id}/{y}: wildcard {wild} below exact {exact}')
            rows.append(dict(tool_id=t.id, year=y, exact=exact, wildcard=wild,
                             analysis=t.in_aggregate and t.category != 'acquisition-suite'))
    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED_DIR / 'wildcard_sensitivity.csv', index=False)
    ana = out[out.analysis]
    for y in YEARS:
        a = ana[ana.year == y]
        ij = a[a.tool_id == 'imagej'].iloc[0]
        print(y, f'ImageJ/Fiji share: exact {100 * ij.exact / a.exact.sum():.1f}%, wildcard {100 * ij.wildcard / a.wildcard.sum():.1f}%')


if __name__ == '__main__':
    main()
