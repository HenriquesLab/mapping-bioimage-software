"""Alias precision for the 15 core packages, 2025 (the added packages are in alias_precision_2025).

Same design as the added-package sample: for each package, the open-access 2025
full-text microscopy papers matched by the registry query form the frame; three
disjoint seeded draws of 10 papers per package (census thirds for small frames)
are written as items, and the full-text windows around each name are bundled for
the two annotators (label_replicates, set alias_precision_core_2025).

Run: python -m census.validation.alias_core
"""
from __future__ import annotations

import pandas as pd

from census._registry import build_boolean_query, load_registry
from census.build import build_reporting_audit as ba
from census.validation.replicates import RAW_DIR, VAL_OUT, _write_bundles, atomic_json, draw_replicates

NAME = 'alias_precision_core_2025'
SEED = '20261014-alias-core-v1'
N = 10
COLUMNS = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']


def main() -> None:
    reg = load_registry()
    tools = [t for t in reg.tools if t.scope == 'core']
    queries = {t.id: f'{build_boolean_query(t, reg.context_query)} AND OPEN_ACCESS:Y AND PUB_YEAR:2025' for t in tools}
    frame_rows, parts = [], [[], [], []]
    design = []
    for tid, q in queries.items():
        pmcids = sorted(set(ba.frame_pmcids(q)))
        frame_rows += [dict(stratum=tid, tool_id=tid, year='2025', epmc_id='', pmcid=p) for p in pmcids]
        units = [dict(stratum=tid, tool_id=tid, year='2025', epmc_id='', pmcid=p) for p in pmcids]
        drawn = draw_replicates(units, N, seed=f'{SEED}-{tid}')
        for i, d in enumerate(drawn):
            parts[i] += d
        design.append(dict(stratum=tid, population=len(pmcids), sampled=[len(d) for d in drawn],
                           census=len(pmcids) < 3 * N))
        print(f'{tid}: frame {len(pmcids)}, drawn {[len(d) for d in drawn]}', flush=True)
    frames = RAW_DIR / 'validation_frames'
    frames.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(frame_rows, columns=COLUMNS).to_csv(frames / f'{NAME}_frame.csv', index=False)
    atomic_json(frames / f'{NAME}_frame.json', dict(queries=queries, frame_unit='tool-pmcid within stratum'))
    VAL_OUT.mkdir(parents=True, exist_ok=True)
    for i, part in enumerate(parts, 1):
        pd.DataFrame(part)[COLUMNS].to_csv(VAL_OUT / f'{NAME}_items_r{i}.csv', index=False)
    _write_bundles(NAME, 'alias', parts)
    # same question and labels as the added-package sample; _write_rubric needs earlier labels this set lacks
    rubric = (VAL_OUT / 'alias_precision_2025_RUBRIC.md').read_text()
    (VAL_OUT / f'{NAME}_RUBRIC.md').write_text(rubric.replace('Alias precision sample', 'Alias precision sample, core packages'))
    atomic_json(VAL_OUT / f'{NAME}_design.json', dict(name=NAME, command='alias', seed=SEED,
                replicate_sizes=[len(p) for p in parts], strata=design,
                note='Core packages; same design as alias_precision_2025. Replicates are disjoint.'))
    print('items', [len(p) for p in parts])


if __name__ == '__main__':
    main()
