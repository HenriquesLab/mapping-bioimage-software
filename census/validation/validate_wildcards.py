"""What the trailing wildcard adds to each package's 2025 count.

For every package with a wildcard alias, three disjoint seeded samples of 10
(census thirds below 30) are drawn from the 2025 open-access papers that match
the wildcard query but not the exact one. Each paper's full text, without its
reference list, is searched for the alias followed by any letters or digits.
The first such token is classified:
  exact    - the bare alias (the index had fused it with markup, e.g. a superscript)
  digits   - alias plus digits (a fused citation number or a version, Cellpose3)
  letters  - alias plus letters, kept for review (napari-imagej is caught by the
             hyphen and counts as exact; CellProfilerAnalyst would land here)
  absent   - no token in the article text
Writes data/validation/wildcard_additions_2025.csv (identifiers and tokens only).
"""
from __future__ import annotations

import re

import pandas as pd

from census._paths import DATA_DIR
from census._registry import alias_clause, load_registry
from census.sources.europepmc import _fetch_records, _id_list
from census.validation.replicates import draw_replicates
from census.validation.validate_citations import REF_LIST, full_text

YEAR = 2025
N = 10
SEED = '20261013-wildcards-v1'
OUT = DATA_DIR / 'validation' / 'wildcard_additions_2025.csv'


def classify(text, aliases):
    alt = '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    m = re.search(rf'(?<![A-Za-z0-9])({alt})([A-Za-z0-9]*)', text, re.I)
    if not m:
        return 'absent', ''
    suffix = m.group(2)
    if not suffix:
        return 'exact', ''
    return ('digits' if suffix.isdigit() else 'letters'), (m.group(1) + suffix)[:40]


def main() -> None:
    reg = load_registry()
    ctx = f'({reg.context_query}) AND OPEN_ACCESS:Y AND PUB_YEAR:{YEAR}'
    rows = []
    for tool in reg.tools:
        wild, exact = alias_clause(tool, wildcard=True), alias_clause(tool, wildcard=False)
        if wild == exact:
            continue
        frame = sorted(set(_id_list(f'{wild} AND {ctx} NOT {exact}')))
        parts = draw_replicates(frame, N, seed=f'{SEED}-{tool.id}')
        units = [u for p in parts for u in p]
        pmc = {(r.get('id'), r.get('source')): r.get('pmcid') for r in _fetch_records(units)}
        words = [a for a in tool.aliases if a not in tool.exact_aliases]
        for rep, part in enumerate(parts, start=1):
            for pid, src in part:
                xml = full_text(pmc.get((pid, src)))
                kind, token = classify(REF_LIST.sub(' ', xml), words) if xml else ('no_full_text', '')
                rows.append(dict(tool_id=tool.id, replicate=rep, epmc_id=pid, source=src, frame=len(frame), kind=kind, token=token))
        print(f'{tool.id}: added {len(frame)}, sampled {len(units)}', flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f'wrote {OUT}')
    print(pd.crosstab(out.tool_id, out.kind).to_string())
    let = out[out.kind == 'letters']
    if len(let):
        print('letter suffixes:', let.groupby('tool_id').token.apply(lambda s: sorted(set(s))).to_dict())


if __name__ == '__main__':
    main()
