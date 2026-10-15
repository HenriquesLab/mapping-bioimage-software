"""Compare the Figure 5 research-area keywords with MEDLINE MeSH headings.

Figure 5 assigns each sampled paper to research areas by matching words in its
title and abstract. This check asks whether those keyword flags agree with the
MeSH descriptors that MEDLINE indexers assigned to the same papers. The paper
sample is a stratified subsample of the distinct-paper MED frame of the
Figure 5 corpus, drawn with a fixed seed, so the numbers reproduce exactly.

The mapping of each area to MeSH descriptor patterns lives in
``config/mesh_areas.yml``. Every pattern anchors both ends of a full descriptor
name and is matched case-insensitively, so qualifiers, titles and abstracts
never enter a MeSH label. The mapping was written before any agreement was
examined and is frozen.

Estimates are inverse-probability weighted by each paper's sampling fraction
(N_h/n_h per stratum), so they describe the distinct-paper MED frame rather
than the sample. Comparisons condition on papers with MeSH headings. Reported
intervals are Wilson intervals on the conditional Kish effective sample size,
plus stratified percentile-bootstrap intervals (2,000 replicates) for
agreement, coverage and Cohen's kappa.

Europe PMC's MED source marks a PubMed record, which need not be MEDLINE
indexed. The JSON core responses carry no isInMedline field for these records,
so the per-paper file stores the record's own subset names instead of claiming
MEDLINE indexing.

Outputs (no article text, only identifiers, flags and MeSH-derived labels):
  data/processed/mesh_check_2021_2025.csv         per-area summary and intervals
  data/processed/mesh_check_papers_2021_2025.csv  per-paper flags and labels
  data/raw/mesh/                                  frozen sample and design record
  data/raw/europepmc_mesh/                        Europe PMC response cache

Run from scripts/:
    python -m census.validation.mesh_check              # prepare, fetch, report
    python -m census.validation.mesh_check --offline    # cached responses only
    python -m census.validation.mesh_check --prepare    # redraw the sample only
    python -m census.validation.mesh_check --fetch      # retrieve missing batches
    python -m census.validation.mesh_check --report     # rewrite the tables only
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from census._http import _cache_path, get_json
from census._paths import CONFIG_DIR, PROCESSED_DIR, RAW_DIR
from census.figures import domains as dm
from census.figures import style as fs

AREAS = list(dm.DOMAINS)
NO_AREA = 'No keyword area'
SEED = 20261020
BATCH = 100
TARGET = 3000
FLOOR = 100
BOOTSTRAP = 2000
SOURCE = 'europepmc_mesh'
API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
MAPPING_YML = CONFIG_DIR / 'mesh_areas.yml'
RUN_DIR = RAW_DIR / 'mesh'
SAMPLE_CSV = RUN_DIR / 'sample.csv'
DESIGN_CSV = RUN_DIR / 'sampling_design.csv'
FRAME_CSV = RUN_DIR / 'frame_labels.csv'
DESIGN_JSON = RUN_DIR / 'design.json'
AREA_CSV_NAME = 'mesh_check_2021_2025.csv'
PAPER_CSV_NAME = 'mesh_check_papers_2021_2025.csv'
PREVALENCE_PCT = 50.0  # display rule applied to the areas in Figure 5


# ---------------------------------------------------------------------------
# Area mapping
# ---------------------------------------------------------------------------

def load_mapping() -> dict[str, str]:
    """Area to anchored MeSH descriptor pattern, from config/mesh_areas.yml."""
    mapping = yaml.safe_load(MAPPING_YML.read_text())['areas']
    if set(mapping) != set(AREAS):
        raise ValueError(f'mesh_areas.yml must cover every Figure 5 area: {sorted(set(AREAS) ^ set(mapping))}')
    return mapping


def _patterns() -> dict[str, re.Pattern]:
    return {area: re.compile(pattern, re.I) for area, pattern in load_mapping().items()}


def matches(area: str, names: list[str]) -> bool:
    """Whether any full descriptor name matches the area's mapped pattern."""
    pattern = _patterns()[area]
    return any(pattern.search(name) is not None for name in names)


def extract_mesh(record: dict) -> tuple[list[str], list[str]]:
    """Descriptor names, and the subset flagged as a major topic of the paper."""
    headings = (record.get('meshHeadingList') or {}).get('meshHeading') or []
    return ([h['descriptorName'] for h in headings if h.get('descriptorName')],
            [h['descriptorName'] for h in headings
             if h.get('descriptorName') and h.get('majorTopic_YN') == 'Y'])


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilson(success: float, total: float) -> tuple[float, float]:
    """Wilson score interval for a proportion, tolerant of an empty denominator."""
    if total <= 0:
        return float('nan'), float('nan')
    z = 1.959963984540054
    p = success / total
    den = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / den
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return max(0, centre - half), min(1, centre + half)


def kappa(cells) -> float:
    """Cohen's kappa from a (true positive, false positive, false negative, true negative) count."""
    tp, fp, fn, tn = np.asarray(cells, dtype=float)
    n = tp + fp + fn + tn
    if not n:
        return float('nan')
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 - 1e-14 else float('nan')


def cell_counts(keyword, mesh, weight) -> np.ndarray:
    """Weighted contingency cells in the order kappa() expects."""
    return np.array([weight[keyword & mesh].sum(), weight[keyword & ~mesh].sum(),
                     weight[~keyword & mesh].sum(), weight[~keyword & ~mesh].sum()])


def conditional(keyword, mesh, weight) -> tuple[float, float, float]:
    """Agreement, coverage and kappa, all conditional on papers with MeSH."""
    agree = weight[keyword & mesh].sum() / weight[keyword].sum() if weight[keyword].sum() else float('nan')
    cover = weight[keyword & mesh].sum() / weight[mesh].sum() if weight[mesh].sum() else float('nan')
    return agree, cover, kappa(cell_counts(keyword, mesh, weight))


def ratio_interval(mask, hits, weight) -> tuple[float, float, float]:
    """Wilson interval for a weighted proportion, on the conditional Kish effective n."""
    ww = weight[mask]
    n_eff = ww.sum() ** 2 / (ww @ ww) if len(ww) else 0
    p = weight[mask & hits].sum() / ww.sum() if len(ww) else float('nan')
    return (*wilson(p * n_eff, n_eff), n_eff)


# ---------------------------------------------------------------------------
# Sample design
# ---------------------------------------------------------------------------

def assign_strata(frame: pd.DataFrame, areas: list[str] = None) -> pd.Series:
    """Rarest positive area per paper, ties alphabetical, no match keeps its own stratum."""
    areas = AREAS if areas is None else areas
    counts = frame[areas].sum()
    order = sorted(areas, key=lambda a: (counts[a], a))
    matrix = frame[areas].to_numpy(bool)[:, [areas.index(a) for a in order]]
    first = matrix.argmax(axis=1)
    return pd.Series(np.where(matrix.any(axis=1), np.array(order)[first], NO_AREA), index=frame.index)


def draw_sample(frame: pd.DataFrame, target: int = TARGET, seed: int = SEED,
                floor: int = FLOOR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One simple random sample per stratum: a floor of 100, then proportional capacity."""
    sizes = frame.groupby('stratum', sort=True).size()
    target = min(target, len(frame))
    alloc = np.minimum(sizes, floor).astype(int)
    if alloc.sum() > target:
        raise ValueError('target too small for the per-stratum floor')
    while alloc.sum() < target:
        capacity = sizes - alloc
        remainder = target - int(alloc.sum())
        ideal = capacity / capacity.sum() * remainder
        add = np.minimum(np.floor(ideal).astype(int), capacity)
        if not add.sum():
            add.loc[ideal.idxmax()] = 1
        alloc += add
    rng = np.random.default_rng(seed)
    parts = []
    for stratum, size in alloc.items():
        sub = frame[frame.stratum == stratum].sort_values('pmid')
        chosen = sub.iloc[rng.choice(len(sub), int(size), replace=False)].copy()
        chosen['selection_probability'] = size / len(sub)
        parts.append(chosen)
    sample = pd.concat(parts).sort_values('pmid').reset_index(drop=True)
    design = pd.DataFrame({'N': sizes, 'n': alloc}).reset_index()
    if len(sample) != target or sample.pmid.nunique() != target:
        raise ValueError('sample is not one distinct paper per unit')
    return sample, design


# ---------------------------------------------------------------------------
# Europe PMC retrieval
# ---------------------------------------------------------------------------

def expected_params(pmids: list[str]) -> dict:
    """Query parameters for one batch; the response cache is keyed by these."""
    return {'query': '(' + ' OR '.join('EXT_ID:' + p for p in pmids) + ') AND SRC:MED',
            'resultType': 'core', 'format': 'json', 'pageSize': BATCH}


def cache_path(params: dict) -> Path:
    """Cache location the shared HTTP helper uses for this request."""
    return _cache_path(SOURCE, API, params)


def batches(frame: pd.DataFrame) -> list[tuple[list[str], Path]]:
    """Sorted identifier batches with their cache paths, in request order."""
    ids = sorted(frame.pmid.astype(str))
    out = []
    for start in range(0, len(ids), BATCH):
        chunk = ids[start:start + BATCH]
        out.append((chunk, cache_path(expected_params(chunk))))
    return out


def check_response(data: dict, requested: list[str]) -> list[dict]:
    """Reject a truncated, misidentified or duplicated batch before it is used."""
    if 'resultList' not in data:
        raise ValueError('Europe PMC response has no resultList')
    results = data['resultList'].get('result') or []
    if int(data['hitCount']) > BATCH:
        raise ValueError('Europe PMC response needs pagination')
    if len(results) != int(data['hitCount']):
        raise ValueError('Europe PMC response is truncated')
    if any(str(r['id']) not in requested or r['source'] != 'MED' for r in results):
        raise ValueError('Europe PMC response holds other identifiers or sources')
    if len({r['id'] for r in results}) != len(results):
        raise ValueError('Europe PMC response repeats an identifier')
    return results


def fetch(frame: pd.DataFrame, offline: bool = False, max_batches: int | None = None) -> int:
    """Retrieve missing MeSH batches; offline mode only reads cached responses."""
    plan = batches(frame)
    missing = [(chunk, path) for chunk, path in plan if not path.exists()]
    if offline and missing:
        raise RuntimeError(f'offline mode: {len(missing)} of {len(plan)} cached MeSH responses are '
                           f'missing (first {missing[0][1].name}); rerun without --offline to fetch')
    fetched = 0
    for chunk, path in plan:
        params = expected_params(chunk)
        if path.exists():
            check_response(json.loads(path.read_text()), chunk)
            continue
        if max_batches is not None and fetched >= max_batches:
            break
        try:
            check_response(get_json(SOURCE, API, params), chunk)
        except ValueError:
            path.unlink(missing_ok=True)  # never trust a cached bad response
            raise
        fetched += 1
    cached = sum(path.exists() for _, path in plan)
    print(f'MeSH responses cached: {cached} of {len(plan)} batches ({fetched} fetched now)')
    return fetched


# ---------------------------------------------------------------------------
# Prepare: the frozen sample
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def med_frame() -> pd.DataFrame:
    """Distinct MED-source papers of the Figure 5 corpus with their keyword flags.

    The corpus files carry no source column, so each row's source is recovered by
    an exact (tool_id, year, epmc_id) join against the replicate response caches.
    """
    d = dm.load_corpus()
    if len(fs.analysis_tools()) != 22 or {'jupyter', 'matlab'} & set(d.tool_id):
        raise ValueError('Figure 5 package set changed; the frozen sample no longer applies')
    ids = pd.read_csv(fs.PROCESSED / 'random_sample_2021_2025_ids.csv', dtype={'epmc_id': str})
    text_ids = pd.read_csv(fs.PROCESSED / 'random_sample_2021_2025.csv.gz',
                           usecols=['tool_id', 'year', 'epmc_id'], dtype={'epmc_id': str})
    if not ids[['tool_id', 'year', 'epmc_id']].equals(text_ids):
        raise ValueError('identifier and text sample files disagree')
    if set(d.year) != set(range(2021, 2026)):
        raise ValueError('Figure 5 corpus years changed; the frozen sample no longer applies')
    lookup: dict[tuple[str, int, str], set[str]] = collections.defaultdict(set)
    provenance = []
    for tool, year in d[['tool_id', 'year']].drop_duplicates().itertuples(index=False, name=None):
        path = RAW_DIR / 'replicates' / 'abstracts' / f'{tool}_{year}.json'
        if not path.exists():
            raise SystemExit(f'missing {path}; the source caches are needed to rebuild the sample')
        blob = json.loads(path.read_text())
        provenance.append({'path': str(path), 'sha256': _sha256(path)})
        for row in blob['rows']:
            lookup[(str(tool), int(year), str(row['epmc_id']))].add(row['source'])
    sources = [lookup[(str(r.tool_id), int(r.year), str(r.epmc_id))] for r in d.itertuples()]
    ambiguous = sum(len(s) != 1 for s in sources)
    if ambiguous:
        raise ValueError(f'{ambiguous} corpus rows have missing or ambiguous source; refusing to infer')
    d['source'] = [next(iter(s)) for s in sources]
    source_counts = d.source.value_counts().to_dict()
    figure_rows = len(d)
    d = d[d.source == 'MED'].copy()
    d['pmid'] = d.epmc_id.astype(str)
    if not d.pmid.str.fullmatch(r'[0-9]+').all():
        raise ValueError('MED frame holds non-numeric identifiers')
    conflicts = d.groupby('pmid')[AREAS].nunique().gt(1).any(axis=1)
    if conflicts.any():
        raise ValueError(f'{int(conflicts.sum())} PMIDs have inconsistent keyword labels')
    frame = d.groupby('pmid', sort=True)[AREAS].first().reset_index()
    frame['year'] = d.groupby('pmid').year.min().reindex(frame.pmid).to_numpy()
    frame['figure_row_count'] = d.groupby('pmid').size().reindex(frame.pmid).to_numpy()
    frame['figure_weight_sum'] = d.groupby('pmid').w.sum().reindex(frame.pmid).to_numpy()
    frame['stratum'] = assign_strata(frame)
    meta = {
        'seed': SEED, 'target': TARGET, 'floor': FLOOR, 'batch': BATCH,
        'figure_rows': figure_rows,
        'figure_distinct_papers': int(text_ids[text_ids.tool_id.isin(fs.analysis_tools())].epmc_id.nunique()),
        'source_counts_figure_rows': source_counts,
        'med_rows': len(d), 'med_distinct_papers': len(frame),
        'tool_ids': fs.analysis_tools(),
        'stratification': 'Each paper takes its rarest positive keyword area in the MED frame, ties '
                          'alphabetical; papers with no match take a No keyword area stratum. Allocation '
                          'is min(100, N_h) per stratum, then proportional to remaining capacity with '
                          'deterministic integer rounding, then simple random sampling without '
                          'replacement per stratum.',
        'source_recovery': 'The corpus carries no source column; each row joins on (tool_id, year, '
                           'epmc_id) to data/raw/replicates/abstracts/<tool>_<year>.json. Missing or '
                           'ambiguous joins stop the run rather than being inferred.',
        'weight_rule': 'Validation weights are N_h/n_h per stratum, so estimates describe the '
                       'distinct-paper MED frame. They are not the Figure 5 package-year weights.',
        'source_provenance': provenance,
        'input_sha256': {str(p): _sha256(p) for p in
                         [fs.PROCESSED / 'random_sample_2021_2025.csv.gz',
                          fs.PROCESSED / 'random_sample_2021_2025_ids.csv',
                          Path(dm.__file__), Path(fs.__file__), MAPPING_YML]},
    }
    return frame, meta


def prepare() -> pd.DataFrame:
    """Redraw the frozen seeded sample from the local corpus and record its design."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    frame, meta = med_frame()
    sample, design = draw_sample(frame)
    if not sample[AREAS].sum().gt(0).all():
        raise ValueError('a sampled area has no positive keyword flag')
    sample.to_csv(SAMPLE_CSV, index=False)
    design.to_csv(DESIGN_CSV, index=False)
    frame.drop(columns=['figure_weight_sum']).to_csv(FRAME_CSV, index=False)
    meta['sample_n'] = len(sample)
    DESIGN_JSON.write_text(json.dumps(meta, indent=2))
    print(f"sampled {meta['sample_n']:,} distinct papers from {meta['med_distinct_papers']:,} MED-frame papers "
          f"(Figure 5: {meta['figure_rows']:,} rows)")
    print(design.to_string(index=False))
    return sample


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def load_sample() -> pd.DataFrame:
    if not SAMPLE_CSV.exists():
        raise SystemExit(f'missing {SAMPLE_CSV}; run `python -m census.validation.mesh_check --prepare` first')
    return pd.read_csv(SAMPLE_CSV, dtype={'pmid': str})


def load_labels(sample: pd.DataFrame) -> pd.DataFrame:
    """Per-paper workspace: identifiers, keyword flags and MeSH-match flags only."""
    records: dict[str, dict] = {}
    for chunk, path in batches(sample):
        if not path.exists():
            raise RuntimeError(f'missing cached MeSH response {path.name}; rerun with --fetch')
        records.update({str(r['id']): r for r in check_response(json.loads(path.read_text()), chunk)})
    names = [extract_mesh(records.get(pmid, {})) for pmid in sample.pmid]
    labels = sample.copy()
    labels['returned'] = labels.pmid.isin(records)
    labels['has_mesh'] = [bool(descriptors) for descriptors, _ in names]
    labels['is_in_medline'] = [medline_status(records.get(pmid, {})) for pmid in labels.pmid]
    for area in AREAS:
        labels['mesh_any__' + area] = [matches(area, descriptors) for descriptors, _ in names]
        labels['mesh_major__' + area] = [matches(area, major) for _, major in names]
    return labels


def medline_status(record: dict) -> str:
    """MEDLINE indexing as the record reports it, never inferred beyond its own fields.

    Europe PMC returns no isInMedline field for these MED records, so the status
    falls back to the subset names the record does carry (Index Medicus is the
    MEDLINE subset) and is otherwise unknown. A paper-level flag is not evidence
    that every sampled paper is MEDLINE indexed.
    """
    for field in ('isInMedline', 'inMedline'):
        if record.get(field):
            return str(record[field])
    subsets = [s.get('name') for s in (record.get('subsetList') or {}).get('subset', []) if s.get('name')]
    return '+'.join(subsets) if subsets else 'unknown'


def paper_columns() -> list[str]:
    return (['pmid', 'year', 'stratum', 'selection_probability', 'figure_row_count',
             'figure_weight_sum', 'returned', 'has_mesh', 'is_in_medline']
            + AREAS + ['mesh_any__' + a for a in AREAS] + ['mesh_major__' + a for a in AREAS])


def summarise(labels: pd.DataFrame) -> pd.DataFrame:
    """Per-area counts, weighted agreement, coverage and kappa, with intervals."""
    precision = fs.load('domain_precision_2025.csv').set_index('area')
    basew = 1 / labels.selection_probability.to_numpy()
    available = labels.has_mesh.to_numpy()
    sub = labels[available]
    weight = basew[available]
    # Bootstrap whole strata, then select the MeSH-available papers, so missing
    # headings contribute their variation. Census strata keep a multiplier of 1.
    rng = np.random.default_rng(SEED + 1)
    multipliers = np.zeros((BOOTSTRAP, len(labels)), dtype=np.int16)
    for _, idx in labels.groupby('stratum').groups.items():
        idx = np.asarray(list(idx))
        if np.isclose(labels.selection_probability.iloc[idx[0]], 1):
            multipliers[:, idx] = 1
        else:
            multipliers[:, idx] = rng.multinomial(len(idx), np.full(len(idx), 1 / len(idx)), size=BOOTSTRAP)
    boot_weight = multipliers * basew[None, :] * available[None, :]
    rows = []
    for area in AREAS:
        keyword = sub[area].to_numpy(bool)
        mesh = sub['mesh_any__' + area].to_numpy(bool)
        major = sub['mesh_major__' + area].to_numpy(bool)
        row = {'area': area, 'shown_in_figure': bool(precision.loc[area, 'shown']),
               'n_keyword_sample': int(labels[area].sum()),
               'n_keyword_with_mesh': int(keyword.sum()),
               'n_mesh_matched': int(mesh.sum()),
               'n_both': int((keyword & mesh).sum()),
               'n_mesh_major_matched': int(major.sum()),
               'n_both_major': int((keyword & major).sum()),
               'n_available': len(sub),
               'annotator_precision': float(precision.loc[area, 'precision'])}
        for label, mesh_label in [('any', mesh), ('major', major)]:
            agree, cover, kap = conditional(keyword, mesh_label, weight)
            row.update({f'agreement_{label}': agree, f'coverage_{label}': cover, f'kappa_{label}': kap})
            for metric, mask, hits in [('agreement', keyword, mesh_label), ('coverage', mesh_label, keyword)]:
                lo, hi, n_eff = ratio_interval(mask, hits, weight)
                raw_n, raw_hits = int(mask.sum()), int((mask & hits).sum())
                raw_lo, raw_hi = wilson(raw_hits, raw_n)
                row.update({f'{metric}_{label}_wilson_lo': lo, f'{metric}_{label}_wilson_hi': hi,
                            f'{metric}_{label}_effective_n': n_eff,
                            f'{metric}_{label}_raw': raw_hits / raw_n if raw_n else float('nan'),
                            f'{metric}_{label}_raw_wilson_lo': raw_lo,
                            f'{metric}_{label}_raw_wilson_hi': raw_hi})
            row[f'kappa_{label}_raw'] = kappa(cell_counts(keyword, mesh_label, np.ones(len(keyword))))
            whole = labels[area].to_numpy(bool)
            whole_mesh = labels['mesh_' + label + '__' + area].to_numpy(bool)
            tp = boot_weight[:, whole & whole_mesh].sum(axis=1)
            fp = boot_weight[:, whole & ~whole_mesh].sum(axis=1)
            fn = boot_weight[:, ~whole & whole_mesh].sum(axis=1)
            tn = boot_weight[:, ~whole & ~whole_mesh].sum(axis=1)
            total = tp + fp + fn + tn
            with np.errstate(divide='ignore', invalid='ignore'):
                po = (tp + tn) / total
                pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (total * total)
                replicates = {'agreement': tp / (tp + fp), 'coverage': tp / (tp + fn),
                              'kappa': (po - pe) / (1 - pe)}
            for metric, values in replicates.items():
                finite = values[np.isfinite(values)]
                row[f'{metric}_{label}_boot_valid_n'] = len(finite)
                lo, hi = np.quantile(finite, [.025, .975]) if len(finite) else [float('nan')] * 2
                row[f'{metric}_{label}_boot_lo'] = lo
                row[f'{metric}_{label}_boot_hi'] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def report() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write the per-area and per-paper tables from cached responses. No network."""
    sample = load_sample()
    labels = load_labels(sample)
    areas = summarise(labels)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    labels[paper_columns()].to_csv(PROCESSED_DIR / PAPER_CSV_NAME, index=False)
    areas.to_csv(PROCESSED_DIR / AREA_CSV_NAME, index=False)
    total, nmesh = len(labels), int(labels.has_mesh.sum())
    shown = areas[areas.shown_in_figure]
    print(f'MeSH available for {nmesh:,} of {total:,} sampled papers ({100 * nmesh / total:.1f}%)')
    print(f'Displayed areas: n {int(shown.n_keyword_with_mesh.min())}-{int(shown.n_keyword_with_mesh.max())} '
          f'keyword-positive papers with MeSH; kappa {shown.kappa_any.min():.2f}-{shown.kappa_any.max():.2f}')
    table = ['| Area | n keyword (MeSH) | Agreement % (Wilson 95%) | Major % | Coverage % (Wilson 95%) | Kappa (bootstrap 95%) |',
             '|---|---:|---:|---:|---:|---:|']
    for r in areas.itertuples(index=False):
        def pct(value):
            return f'{100 * value:.1f}'
        table.append(f'| {r.area} | {r.n_keyword_with_mesh} | '
                     f"{pct(r.agreement_any)} ({pct(r.agreement_any_wilson_lo)}–{pct(r.agreement_any_wilson_hi)}) | "
                     f"{pct(r.agreement_major)} | "
                     f"{pct(r.coverage_any)} ({pct(r.coverage_any_wilson_lo)}–{pct(r.coverage_any_wilson_hi)}) | "
                     f'{r.kappa_any:.2f} ({r.kappa_any_boot_lo:.2f}–{r.kappa_any_boot_hi:.2f}) |')
    print('\n'.join(table))
    return areas, labels


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--prepare', action='store_true', help='redraw the frozen sample from the local corpus')
    parser.add_argument('--fetch', action='store_true', help='retrieve the missing Europe PMC responses')
    parser.add_argument('--report', action='store_true', help='write the processed tables from cached responses')
    parser.add_argument('--offline', action='store_true', help='never make a network request')
    parser.add_argument('--max-batches', type=int, default=None, help='fetch at most this many batches')
    args = parser.parse_args(argv)
    steps = [s for s in ('prepare', 'fetch', 'report') if getattr(args, s)] or ['prepare', 'fetch', 'report']
    sample = prepare() if 'prepare' in steps else None
    if 'fetch' in steps:
        fetch(sample if sample is not None else load_sample(), offline=args.offline,
              max_batches=args.max_batches)
    elif args.offline:
        fetch(load_sample(), offline=True)
    if 'report' in steps:
        report()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
