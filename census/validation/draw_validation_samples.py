"""Fresh validation draws. Historical label sets have unrecovered drawing provenance.

Four commands: cellpose, alias, lexicon, domains. Outputs contain identifiers and
stratum keys only; annotation is a separate manual step. A new string seed is
recorded, never attributed to the historical labels. Save the frame CSV and its
JSON sidecar to reproduce a draw without network access (use --frame).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

import pandas as pd

from census._paths import CONFIG_DIR, DATA_DIR, PACKAGE_DIR, PROCESSED_DIR, RAW_DIR
from census._registry import build_boolean_query, load_registry
from census.build.build_reporting_audit import frame_pmcids
from census.build.classify_dl import is_deep_learning, lexicon_version

NAMES = {'cellpose': 'cellpose_workflow_2025', 'alias': 'alias_precision_2025',
         'lexicon': 'dl_lexicon_2021_2025', 'domains': 'domain_keywords_2021_2025'}
COLUMNS = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
DEFAULT_SEED = '20261006-validation-redraw-v1'  # New draw, not a recovered seed.
ALIAS_TOOLS = ['zen', 'lasx', 'amira', 'huygens', 'dragonfly', 'aivia', 'halo',
               'metamorph', 'volocity', 'cellsens', 'nis', 'skimage', 'opencv',
               'visiopharm', 'axiovision']
CORPUS = PROCESSED_DIR / 'random_sample_2021_2025.csv.gz'
PATTERNS = CONFIG_DIR / 'domain_validation_keywords.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalise(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f'frame is missing columns: {sorted(missing)}')
    d = frame[COLUMNS].fillna('').astype(str)
    if d.empty or (d.stratum == '').any() or ((d.epmc_id == '') & (d.pmcid == '')).any():
        raise ValueError('frame needs non-empty strata and identifiers')
    if d.duplicated(COLUMNS).any():
        raise ValueError('duplicate sampling units in frame')
    return d.sort_values(COLUMNS).reset_index(drop=True)


def validate_frame(frame: pd.DataFrame, command: str) -> None:
    """Reject a frame from another design, even when its column schema matches."""
    d = normalise(frame)
    reg = load_registry()
    expected = ({'cellpose'} if command == 'cellpose' else set(ALIAS_TOOLS) if command == 'alias'
                else {'lex_pos', 'lex_neg'} if command == 'lexicon'
                else set(json.loads(PATTERNS.read_text())))
    if set(d.stratum) != expected:
        raise ValueError(f'{command}: frame strata differ from the specified design')
    if command in ('cellpose', 'alias'):
        valid = ((d.tool_id == d.stratum) & (d.year == '2025') & (d.epmc_id == '')
                 & d.pmcid.str.fullmatch(r'PMC[0-9]+'))
    else:
        tools = ([t.id for t in reg.core_tools if t.in_aggregate] if command == 'lexicon'
                 else [t.id for t in reg.tools if t.in_aggregate and t.category != 'acquisition-suite'])
        valid = (d.tool_id.isin(tools) & d.year.isin([str(y) for y in range(2021, 2026)])
                 & (d.epmc_id != '') & (d.pmcid == ''))
    if not valid.all():
        raise ValueError(f'{command}: frame has invalid tool, year or identifier fields')

def corpus_frame(corpus: pd.DataFrame, command: str) -> pd.DataFrame:
    """Package-paper units, not deduplicated papers. Area strata may overlap."""
    reg = load_registry()
    tools = ([t.id for t in reg.core_tools if t.in_aggregate] if command == 'lexicon'
             else [t.id for t in reg.tools if t.in_aggregate and t.category != 'acquisition-suite'])
    d = corpus[corpus.tool_id.isin(tools) & corpus.year.between(2021, 2025)].copy().fillna('')
    d['epmc_id'] = d.epmc_id.astype(str)
    d['pmcid'] = ''  # Corpus retains epmc_id, not pmcid or source.
    text = d.title + ' ' + d.abstract
    if command == 'lexicon':
        d['stratum'] = text.map(lambda s: 'lex_pos' if is_deep_learning(s) else 'lex_neg')
        return normalise(d[COLUMNS])
    text = text.map(lambda s: re.sub(r'<[^>]+>', ' ', s).lower())
    chunks = []
    for area, pattern in json.loads(PATTERNS.read_text()).items():
        g = d[text.str.contains(pattern, regex=True)].copy()
        g['stratum'] = area
        chunks.append(g[COLUMNS])
    return normalise(pd.concat(chunks, ignore_index=True))


def build_frame(command: str) -> tuple[pd.DataFrame, dict]:
    reg = load_registry()
    if command in ('lexicon', 'domains'):
        frame = corpus_frame(pd.read_csv(CORPUS, dtype={'epmc_id': str}), command)
        extra = {'corpus': CORPUS.relative_to(DATA_DIR.parent).as_posix(), 'corpus_sha256': sha256(CORPUS),
                 'registry_sha256': sha256(CONFIG_DIR / 'tools.yml'),
                 'frame_unit': 'tool-year-epmc_id within stratum'}
        if command == 'lexicon':
            extra.update(lexicon_version=lexicon_version(),
                         classifier_sha256=sha256(PACKAGE_DIR / 'build' / 'classify_dl.py'),
                         lexicon_sha256=sha256(CONFIG_DIR / 'dl_lexicon.yml'))
        else:
            extra.update(patterns_sha256=sha256(PATTERNS))
        return frame, extra
    if command == 'cellpose':
        q = (f'{build_boolean_query(reg.by_id("cellpose"), reg.context_query)} AND '
             f'{build_boolean_query(reg.by_id("imagej"), "")} AND OPEN_ACCESS:Y AND PUB_YEAR:2025')
        queries = {'cellpose': q}
    else:
        # Fresh annotation frame explicitly requires OA and an available PMCID.
        queries = {t: f'{build_boolean_query(reg.by_id(t), reg.context_query)} AND OPEN_ACCESS:Y AND PUB_YEAR:2025'
                   for t in ALIAS_TOOLS}
    rows = []
    for stratum, query in queries.items():
        for pmcid in frame_pmcids(query):  # Existing paged _http.get_json cache helper.
            rows.append(dict(stratum=stratum, tool_id=stratum, year='2025', epmc_id='', pmcid=pmcid))
    return normalise(pd.DataFrame(rows, columns=COLUMNS)), {'queries': queries,
                'registry_sha256': sha256(CONFIG_DIR / 'tools.yml'), 'frame_unit': 'tool-pmcid within stratum'}


def draw(frame: pd.DataFrame, sizes: dict[str, int], seed: str, command: str) -> tuple[pd.DataFrame, list[dict]]:
    if not isinstance(seed, str) or not seed:
        raise ValueError('seed must be a non-empty string')
    d = normalise(frame)
    chunks, design = [], []
    for stratum, g in d.groupby('stratum', sort=True):
        requested = sizes[stratum]
        if requested < 0:
            raise ValueError('sample size must be non-negative')
        n = min(requested, len(g))
        derived = f'{seed}-{command}-{stratum}'
        chosen = random.Random(derived).sample(list(g.index), n)
        chunks.append(d.loc[chosen])
        design.append(dict(stratum=stratum, population=len(g), sampled=n,
                           sampling_fraction=n / len(g), seed=derived,
                           replacement=False, census=n == len(g)))
    return pd.concat(chunks).sort_values(COLUMNS).reset_index(drop=True), design


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    for name in NAMES:
        p = sub.add_parser(name)
        p.add_argument('--seed', default=DEFAULT_SEED, help='new recorded string seed')
        p.add_argument('--frame', type=Path, help='frozen identifier frame CSV, no network')
        p.add_argument('--output-dir', type=Path, default=DATA_DIR / 'validation')
        p.add_argument('--replicates', action='store_true',
                       help='draw three disjoint replicates into data/validation/replicates; '
                            'leave the single-draw outputs unchanged')
    a = ap.parse_args(argv)
    if a.replicates:
        from census.validation.replicates import validation
        validation(sets=[a.command])
        return
    dest = a.output_dir / (NAMES[a.command] + '_items.csv')
    meta_path = dest.with_suffix('.json')
    if dest.exists() or meta_path.exists():
        raise FileExistsError(f'refusing to overwrite draw: {dest}; use a new --output-dir')
    extra = {}
    frame_path = a.frame or DATA_DIR / 'validation' / 'frames' / (NAMES[a.command] + '_frame.csv')
    if frame_path.exists():
        frame = normalise(pd.read_csv(frame_path, dtype=str, keep_default_na=False))
        sidecar = frame_path.with_suffix('.json')
        extra = json.loads(sidecar.read_text()) if sidecar.exists() else {'origin': 'user-supplied frozen frame'}
        if extra.get('frame_sha256', sha256(frame_path)) != sha256(frame_path):
            raise ValueError('frozen frame hash does not match its sidecar')
    elif a.frame:
        raise FileNotFoundError(a.frame)
    else:
        frame, extra = build_frame(a.command)
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(frame_path, index=False, mode='x')
        extra['frame_sha256'] = sha256(frame_path)
        frame_path.with_suffix('.json').write_text(json.dumps(extra, indent=2) + '\n')
    validate_frame(frame, a.command)
    sizes = {s: (80 if s == 'lex_pos' else 120) if a.command == 'lexicon'
             else {'cellpose': 40, 'alias': 10, 'domains': 8}[a.command]
             for s in frame.stratum.unique()}
    if a.command == 'lexicon' and set(sizes) != {'lex_pos', 'lex_neg'}:
        raise ValueError('lexicon frame must contain both lex_pos and lex_neg only')
    items, design = draw(frame, sizes, a.seed, a.command)
    meta = dict(command=a.command, seed=a.seed, historical_draw_recovered=False,
                frame=str(frame_path.resolve().relative_to(DATA_DIR.parent)) if frame_path.resolve().is_relative_to(DATA_DIR.parent) else str(frame_path.resolve()), frame_sha256=sha256(frame_path),
                drawing_code_sha256=sha256(Path(__file__)), design=design, inputs=extra,
                pooling='No automatic pooling weights. Use frame N/n for stratum population inference; corpus tool-year weights are a separate stage.')
    a.output_dir.mkdir(parents=True, exist_ok=True)
    items.to_csv(dest, index=False, mode='x')
    with meta_path.open('x') as fh:
        fh.write(json.dumps(meta, indent=2) + '\n')
    print(f'{a.command}: {len(items)} identifier items -> {dest}; new draw requires annotation')


if __name__ == '__main__':
    main()
