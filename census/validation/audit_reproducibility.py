"""Cache-only reproducibility probes; never change published data or call the network.

Run after drawing fresh validation items. Results go to data/raw/code_audit/.
Optional --historical-corpus accepts the corpus at the label-introduction commit.
Candidate seeds are exploratory tests, not claims about historical provenance.
"""
from __future__ import annotations

import argparse
import importlib
import json
import random
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from census import _http
from census._paths import DATA_DIR, PACKAGE_DIR, PROCESSED_DIR, RAW_DIR


def cached_json(source, url, params=None, **kwargs):
    path = _http._cache_path(source, url, params)
    if not path.exists():
        raise FileNotFoundError(f'cache miss: {source}/{path.name}')
    return json.loads(path.read_text())


def compare_csv(path: Path, original: Path) -> dict:
    a, b = pd.read_csv(path), pd.read_csv(original)
    try:
        pd.testing.assert_frame_equal(a, b)
        return {'exact_dataframe': True, 'rows': len(a)}
    except AssertionError as exc:
        return {'exact_dataframe': False, 'rows': len(a), 'difference': str(exc)[:500]}


def candidates(frame, labels, command):
    """Compare unordered identifier sets within each stratum, not label values."""
    from census.validation import draw_validation_samples as draw
    if command == 'cellpose':
        keys, strat = ['pmcid'], None
    elif command == 'alias':
        keys, strat = ['tool_id', 'pmcid'], 'tool_id'
    elif command == 'lexicon':
        keys, strat = ['tool_id', 'year', 'epmc_id'], 'stratum'
    else:
        keys, strat = ['tool_id', 'epmc_id'], 'area'
    labels = labels.fillna('').astype(str)
    frame = draw.normalise(frame)
    expected = {s: set(map(tuple, g[keys].to_numpy())) for s, g in labels.groupby(strat)} if strat else {
        'cellpose': set(map(tuple, labels[keys].to_numpy()))}
    available = {s: set(map(tuple, g[keys].to_numpy())) for s, g in frame.groupby('stratum')}
    membership = {s: {'labelled': len(ids), 'in_frame': len(ids & available.get(s, set())),
                      'population': len(available.get(s, set()))} for s, ids in expected.items()}
    # Common seed and date candidates only. A failed bounded search cannot prove
    # that no historical seed exists. Historical frame order may also differ.
    seeds = [1, 42, 20260929, 20261001, 20261002, 20261006]
    matches, tested = [], 0
    groups = [(s, g) for s, g in frame.groupby('stratum', sort=True) if s in expected]
    for seed in seeds:
        for mode in ('integer-shared', 'string-shared', 'integer-per-stratum',
                     'string-per-stratum', 'string-suffix', 'new-convention'):
            shared = random.Random(str(seed) if mode == 'string-shared' else seed)
            observed = {}
            for s, g in groups:
                n = len(expected[s])
                rng = (shared if mode.endswith('shared') else random.Random(
                    seed if mode == 'integer-per-stratum' else str(seed) if mode == 'string-per-stratum'
                    else f'{seed}-{s}' if mode == 'string-suffix' else f'{seed}-{command}-{s}'))
                ids = rng.sample(list(g.index), min(n, len(g)))
                observed[s] = set(map(tuple, frame.loc[ids, keys].to_numpy()))
            tested += 1
            if observed == expected:
                matches.append({'seed': seed, 'mode': mode})
    return {'membership': membership, 'candidate_draws_tested': tested,
            'exact_identifier_matches': matches, 'historical_provenance_recovered': False}


def rebuild_dl(out: Path, reg) -> None:
    """Consume the rebuilt upstream counts, so dependency differences stay visible."""
    from census.build import build_dataset
    build_dataset.build_dl(reg, pd.read_csv(out / 'literature_yearly.csv'), 200)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--historical-corpus', type=Path)
    args = ap.parse_args()
    # Patch before importing callers that capture get_json by name.
    _http.get_json = cached_json
    from census.validation import draw_validation_samples as draw
    from census.build import build_dataset as bd
    from census.build import build_reporting_audit as ba
    from census.validation import validate_reporting_audit as va
    from census._registry import load_registry
    result = {'network': 'disabled', 'processed': {}, 'historical_probes': {}}
    reg = load_registry()
    # Import every census module recursively. This covers the figure modules too;
    # the tests, imported here before the package layout, run under pytest instead.
    modules = []
    for path in sorted(PACKAGE_DIR.rglob('*.py')):
        parts = path.relative_to(PACKAGE_DIR).with_suffix('').parts
        if 'tests' in parts:
            continue
        if parts[-1] == '__init__':
            parts = parts[:-1]
        modules.append('.'.join(('census', *parts)))
    result['imports'] = []
    for name in modules:
        importlib.import_module(name)
        result['imports'].append(name)
    with tempfile.TemporaryDirectory(dir=RAW_DIR) as tmp:
        out = Path(tmp)
        bd.PROCESSED_DIR = out
        steps = [('tools', lambda: bd.write_tools(reg)), ('literature', lambda: bd.build_literature(reg)),
                 ('corpus', lambda: bd.build_corpus(reg)),
                 ('deep_learning', lambda: rebuild_dl(out, reg))]
        for name, action in steps:
            try:
                action()
                result[name] = 'completed from cache'
            except Exception as exc:
                result[name] = f'{type(exc).__name__}: {exc}'
        for modname in ('census.build.build_hosts', 'census.build.build_methods_check',
                        'census.build.build_sensitivity', 'census.build.build_dataset_dl_in_tools',
                        'census.build.build_dataset_dl_within_tools', 'census.build.random_corpus'):
            mod = importlib.import_module(modname)
            mod.PROCESSED_DIR = out
            if hasattr(mod, 'OUTPUT_CSV'):
                mod.OUTPUT_CSV = out / mod.OUTPUT_CSV.name
            # main argparse uses the OUTPUT_CSV global when creating its parser.
            import sys
            old = sys.argv
            sys.argv = [modname.rsplit('.', 1)[-1] + '.py']
            try:
                mod.main()
            except Exception as exc:
                result[modname] = f'{type(exc).__name__}: {exc}'
            finally:
                sys.argv = old
        # XML downloads are forbidden too. Cache may contain an empty 404 marker.
        def xml(pmcid):
            path = ba.XML_DIR / f'{pmcid}.xml'
            return path.read_text() or None
        ba.fetch_xml = xml
        ba.PROCESSED_DIR = out
        ba.OUT_RAW = out / 'audit_raw'
        ba.OUT_RAW.mkdir()
        published = pd.read_csv(PROCESSED_DIR / 'reporting_audit_papers_2025.csv')
        result['reporting_draw_identifiers'] = {}
        for tool in ba.TOOLS:
            frame = ba.frame_pmcids(ba.frame_query(reg.by_id(tool), f'({reg.context_query})'))
            chosen = frame if len(frame) <= 200 else sorted(random.Random(f'{ba.SEED}-{tool}-reporting').sample(frame, 200))
            result['reporting_draw_identifiers'][tool] = set(chosen) == set(published[published.tool_id == tool].pmcid)
        try:
            ba.main(200, ba.TOOLS)
        except Exception as exc:
            result['reporting_audit'] = f'{type(exc).__name__}: {exc}'
        # Validate sampling and scoring independently even when full XML replay
        # is incomplete. Use published paper flags as declared inputs here.
        try:
            import shutil
            shutil.copyfile(PROCESSED_DIR / 'reporting_audit_papers_2025.csv', out / 'reporting_audit_papers_2025.csv')
            shutil.copyfile(RAW_DIR / 'reporting_audit/windows_2025.jsonl', ba.OUT_RAW / 'windows_2025.jsonl')
            va.PROCESSED_DIR = out
            va.OUT_RAW = ba.OUT_RAW
            va.sample()
            records = [json.loads(s) for s in (va.OUT_RAW / 'validation_items_2025.jsonl').read_text().splitlines()]
            ids = {r['item_id'] for r in records}
            result['reporting_validation_identifiers'] = {
                p.name: ids == set(pd.read_csv(p).item_id) for p in va.VAL_DIR.glob('reporting_audit_labels_*.csv')}
            va.score()
        except Exception as exc:
            result['reporting_validation'] = f'{type(exc).__name__}: {exc}'
        for path in sorted(out.glob('*.csv*')):
            original = PROCESSED_DIR / path.name
            if original.exists() and not (path.name == 'reporting_audit_papers_2025.csv' and 'reporting_audit' in result):
                result['processed'][path.name] = compare_csv(path, original)
    for command, stem in draw.NAMES.items():
        framepath = DATA_DIR / 'validation' / 'frames' / (stem + '_frame.csv')
        labels = pd.read_csv(DATA_DIR / 'validation' / (stem + '.csv'), dtype=str)
        if framepath.exists():
            result['historical_probes'][command] = candidates(pd.read_csv(framepath, dtype=str, keep_default_na=False), labels, command)
        else:
            result['historical_probes'][command] = {'error': 'fresh candidate frame not available'}
        if args.historical_corpus and command in ('lexicon', 'domains'):
            frame = draw.corpus_frame(pd.read_csv(args.historical_corpus, dtype={'epmc_id': str}), command)
            result['historical_probes'][command + '_historical_corpus'] = candidates(frame, labels, command)
    dest = RAW_DIR / 'code_audit' / 'evidence.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2) + '\n')
    print('Evidence:', dest)
    print('Exact processed reruns:', [k for k,v in result['processed'].items() if v['exact_dataframe']])
    print('Non-matching processed reruns:', [k for k,v in result['processed'].items() if not v['exact_dataframe']])
    print('Historical seed matches:', {k: v.get('exact_identifier_matches', []) for k,v in result['historical_probes'].items()})


if __name__ == '__main__':
    main()
