"""Prepare, summarise and pool seeded validation replicates.

python -m census.validation.replicates draw
python -m census.validation.replicates abstracts
python -m census.validation.replicates audit
python -m census.validation.replicates validation
python -m census.validation.replicates pool
python -m census.validation.replicates summarise

Random-sample frames produce three disjoint seeded samples. A frame shorter
than three times the sample size is treated as a census and split into three
random parts differing by at most one record. Abstract tool-years also split
any frame of at most CENSUS_MAX (2,000) records. The union then covers the frame.
Retrieval resumes from local caches and receipts.

Annotation is a separate manual hand-off through an external agent harness.
Run batches and collect in `census.validation.label_replicates` and
`census.validation.label_round2`. Pooling uses collected labels and the
committed reporting-audit replicate summary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

from census._paths import CONFIG_DIR, DATA_DIR, PROCESSED_DIR, RAW_DIR, TOOLS_YML
from census._registry import build_boolean_query, load_registry
from census.build.classify_dl import is_deep_learning, wilson
from census.sources import europepmc

OUT = PROCESSED_DIR / 'replicates'
RAW = RAW_DIR / 'replicates'
VAL_OUT = DATA_DIR / 'validation' / 'replicates'
ANN_DIR = RAW_DIR / 'annotation'
SEED = '20261006-disjoint-replicates-v1'
CENSUS_MAX = europepmc.CENSUS_MAX

TAG = re.compile(r'<[^>]+>')


def _key(item):
    return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)


def draw_replicates(frame, n, first=None, seed=SEED, census=False):
    """Return three disjoint draws, or balanced random thirds of a small frame.

    Explicit first preserves the historical draw's order and identifiers and is
    used only on the disjoint path. census=True, or a frame shorter than three
    times the sample, keeps every record in three parts differing by at most
    one. Actual RNG seeds are seed-r1/r2/r3, or seed-census-split.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError('n must be a non-negative integer')
    if not isinstance(seed, str) or not seed:
        raise ValueError('seed must be a recorded non-empty string')
    frame = list(frame)
    keyed = {_key(x): x for x in frame}
    if len(keyed) != len(frame):
        raise ValueError('duplicate frame units')
    ordered = [keyed[k] for k in sorted(keyed)]
    if census or len(frame) < 3 * n:
        random.Random(f'{seed}-census-split').shuffle(ordered)
        return [ordered[i::3] for i in range(3)]
    if first is None:
        first = random.Random(f'{seed}-r1').sample(ordered, n)
    first = list(first)
    keys = {_key(x) for x in first}
    if len(first) != n or len(keys) != n or not keys <= keyed.keys():
        raise ValueError('first must contain n distinct frame members')
    parts = [first]
    for r in (2, 3):
        remaining = [x for x in ordered if _key(x) not in keys]
        chosen = random.Random(f'{seed}-r{r}').sample(remaining, n)
        parts.append(chosen)
        keys.update(_key(x) for x in chosen)
    return parts


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False) + '\n')
    tmp.replace(path)


def _read_json(path):
    return json.loads(Path(path).read_text())


# ---------------------------------------------------------------------------
# (a) Abstract samples for the deep-learning and research-area estimates
# ---------------------------------------------------------------------------


def _jobs(tools=None, years=None):
    reg = load_registry()
    raw = yaml.safe_load(TOOLS_YML.read_text())['tools']
    caps = {t['id']: int(t.get('dl_sample_cap', 200)) for t in raw}
    for tool in reg.tools:
        if tools and tool.id not in tools:
            continue
        for year in reg.years:
            if years and year not in years:
                continue
            yield tool, reg, year, caps[tool.id]


def abstract_design(tool, reg, year, cap, seed=SEED):
    """Freeze the ordered API frame and the three draws.

    The historical draw reads the whole frame when the frame is at most
    CENSUS_MAX, otherwise a seeded simple random sample of cap. A frame shorter
    than three times cap is read whole and split into thirds, so its union
    estimate carries no sampling error.
    """
    dest = RAW / 'designs' / f'{tool.id}_{year}.json'
    if dest.exists():
        data = _read_json(dest)
        if data['seed'] != seed or data['cap'] != cap:
            raise ValueError(f'incompatible saved design: {dest}')
        return data
    raw = europepmc._id_list(f'{build_boolean_query(tool, reg.context_query)} AND PUB_YEAR:{year}')
    # A handful of tool-years return one record twice; keep first occurrence so
    # the frame has unique units. Replicate 1 is still drawn from the raw list,
    # matching the committed historical draw.
    pairs = list(dict.fromkeys(raw))
    population = len(pairs)
    historical_seed = f'20260929-{tool.id}-{year}'
    census = population <= CENSUS_MAX or population < 3 * cap
    base = f'{seed}-abstract-{tool.id}-{year}'
    if census:
        parts = draw_replicates(pairs, cap, seed=base, census=True)
        mode = 'census-split'
    else:
        first = random.Random(historical_seed).sample(raw, cap)
        parts = draw_replicates(pairs, cap, first=first, seed=base)
        mode = 'disjoint-srs'
    data = dict(tool_id=tool.id, year=year, cap=cap, population=population,
                duplicate_ids=len(raw) - len(pairs),
                sampling=mode, seed=seed, historical_seed=historical_seed,
                frame_sha256=hashlib.sha256(_key(pairs).encode()).hexdigest(),
                frame=pairs, draws=parts,
                replicate_seeds=([historical_seed, f'{base}-r2', f'{base}-r3']
                                 if mode == 'disjoint-srs' else [f'{base}-census-split']))
    atomic_json(dest, data)
    return data


def draw(tools=None, years=None, seed=SEED, **kwargs):
    count = 0
    for tool, reg, year, cap in _jobs(tools, years):
        abstract_design(tool, reg, year, cap, seed)
        count += 1
    print(f'frozen {count} abstract designs under {RAW / "designs"}')


def abstracts(tools=None, years=None, seed=SEED, seconds=None, max_jobs=None):
    """Retrieve serially through the original polite cached helpers."""
    started, done = time.monotonic(), 0
    for tool, reg, year, cap in _jobs(tools, years):
        dest = RAW / 'abstracts' / f'{tool.id}_{year}.json'
        if dest.exists():
            continue
        if (seconds and time.monotonic() - started >= seconds) or (max_jobs and done >= max_jobs):
            break
        design = abstract_design(tool, reg, year, cap, seed)
        rows = []
        for replicate, chosen in enumerate(design['draws'], 1):
            chosen = [tuple(x) for x in chosen]
            records = europepmc._fetch_records(chosen)
            lookup = {(str(x.get('id', '')), str(x.get('source', ''))): x for x in records}
            missing = [x for x in chosen if x not in lookup]
            if missing:
                raise RuntimeError(f'{tool.id} {year}: {len(missing)} selected records unavailable; no replacement allowed')
            for pair in chosen:
                r = lookup[pair]
                journal = ((r.get('journalInfo') or {}).get('journal') or {})
                rows.append(dict(tool_id=tool.id, year=year, epmc_id=pair[0], source=pair[1],
                                 pmcid=r.get('pmcid', ''), title=r.get('title') or '',
                                 abstract=r.get('abstractText') or '', venue=journal.get('title') or '',
                                 replicate=replicate, population=design['population'],
                                 n_sampled=len(chosen), sampling=design['sampling']))
        atomic_json(dest, {'design': {k: v for k, v in design.items() if k not in ('frame', 'draws')}, 'rows': rows})
        done += 1
        print(f'{tool.id} {year}: {design["sampling"]}, N={design["population"]}, sizes={[len(p) for p in design["draws"]]}', flush=True)
    materialise_abstracts()


def domain_patterns():
    """The research-area patterns, frozen and byte-identical to the manuscript copy."""
    return json.loads((CONFIG_DIR / 'domain_validation_keywords.json').read_text())


def _analysis_tool_ids(reg):
    return {t.id for t in reg.tools if t.in_aggregate and t.category != 'acquisition-suite'}


def materialise_abstracts():
    """Publish identifier-only records and fractions from completed receipts."""
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((RAW / 'abstracts').glob('*.json'))
    if not files:
        return
    reg = load_registry()
    patterns = domain_patterns()
    analysis = _analysis_tool_ids(reg)
    rows, estimates, domains, design_rows = [], [], [], []
    for path in files:
        obj = _read_json(path)
        design = obj['design']
        d = pd.DataFrame(obj['rows'])
        if d.empty:
            for rep in (1, 2, 3):
                estimates.append(dict(tool_id=design['tool_id'], tool=design['tool_id'], year=design['year'], replicate=rep,
                                      n=0, n_dl=0, population=design['population'], dl_share=0.0, dl_fraction=0.0,
                                      sampling=design['sampling'], ci_lo=0.0, ci_hi=0.0, census_estimate=None))
            design_rows.append({k: v for k, v in design.items() if k not in ('frame', 'draws')})
            continue
        d['dl'] = (d.title + ' ' + d.abstract).map(is_deep_learning)
        rows.extend(d.drop(columns=['title', 'abstract', 'venue']).to_dict('records'))
        whole = design['sampling'] == 'census-split'
        overall = float(d.dl.mean())
        for rep in (1, 2, 3):
            g = d[d.replicate == rep]
            p = float(g.dl.mean()) if len(g) else 0.0
            if whole:
                lo = hi = p
            else:
                lo, hi = wilson(int(g.dl.sum()), len(g))
            estimates.append(dict(tool_id=design['tool_id'], tool=design['tool_id'], year=design['year'], replicate=rep,
                                  n=len(g), n_dl=int(g.dl.sum()), population=design['population'], dl_share=p, dl_fraction=p,
                                  sampling=design['sampling'], ci_lo=lo, ci_hi=hi,
                                  census_estimate=overall if whole else None))
            if design['year'] >= 2021 and design['tool_id'] in analysis:
                text = (g.title + ' ' + g.abstract).map(lambda s: TAG.sub(' ', s).lower())
                for name, pattern in patterns.items():
                    share = float(text.str.contains(pattern, regex=True).mean()) if len(g) else 0.0
                    domains.append(dict(tool_id=design['tool_id'], tool=design['tool_id'], year=design['year'], replicate=rep,
                                        n=len(g), population=design['population'], domain=name, share=share,
                                        sampling=design['sampling']))
        design_rows.append({k: v for k, v in design.items() if k not in ('frame', 'draws')})
    pd.DataFrame(rows).to_csv(OUT / 'abstract_samples_replicates.csv.gz', index=False)
    e = pd.DataFrame(estimates)
    lit = pd.read_csv(PROCESSED_DIR / 'literature_yearly.csv').query("source == 'europepmc'")
    counts = lit.set_index(['tool_id', 'year'])['count']
    core = {t.id for t in reg.core_tools if t.in_aggregate}
    pooled = []
    for (year, rep), g in e[e.tool_id.isin(core)].groupby(['year', 'replicate']):
        if set(g.tool_id) != core:
            continue  # A partial batch must never masquerade as a field estimate.
        weights = [counts.get((t, year), 0) for t in g.tool_id]
        count_dl = sum(round(w * round(p, 4)) for w, p in zip(weights, g.dl_share))
        p = count_dl / sum(weights) if sum(weights) else 0.0
        census = float(g.dl_share.where(g.sampling == 'census-split', g.census_estimate).mean()) if (g.sampling == 'census-split').all() else None
        pooled.append(dict(tool_id='field_core', tool='field_core', year=year, replicate=rep,
                           n=int(g.n.sum()), population=int(g.population.sum()), n_dl=int(g.n_dl.sum()),
                           dl_share=p, dl_fraction=p, sampling='weighted-core', ci_lo=None, ci_hi=None,
                           census_estimate=census))
    full = pd.concat([e, pd.DataFrame(pooled)], ignore_index=True)
    full['year'] = full['year'].astype(int)
    full.to_csv(OUT / 'dl_share_replicates.csv', index=False)
    dom = pd.DataFrame(domains)
    if not dom.empty:
        pool = []
        for (tool, rep, domain), g in dom.groupby(['tool_id', 'replicate', 'domain']):
            if set(g.year) != set(range(2021, 2026)):
                continue
            p = float((g['share'] * g.population).sum() / g.population.sum()) if g.population.sum() else 0.0
            pool.append(dict(tool_id=tool, tool=tool, year='2021-2025', replicate=rep,
                             n=int(g.n.sum()), population=int(g.population.sum()), domain=domain, share=p,
                             sampling='weighted-tool-years'))
        pool = pd.DataFrame(pool)
        if not pool.empty:
            for (rep, domain), g in pool.groupby(['replicate', 'domain']):
                weighted = g['share'] * g.population
                denominator = g.population.sum() - g.population
                baseline = (weighted.sum() - weighted) / denominator.where(denominator > 0)
                pool.loc[g.index, 'baseline'] = baseline
                pool.loc[g.index, 'ratio'] = g['share'] / baseline.where(baseline > 0)
        dom = pd.concat([dom, pool], ignore_index=True)
        dom['year'] = dom['year'].astype(str)
        dom.to_csv(OUT / 'domain_share_replicates.csv', index=False)
    atomic_json(OUT / 'abstract_designs.json', dict(seed=SEED, completed_jobs=len(files), expected_jobs=480,
                note='Census-split thirds keep every record and show the spread; their union carries no sampling error. Disjoint-srs keeps the historical replicate 1.', designs=design_rows))
    print(f'published {len(files)}/480 completed abstract jobs, {len(rows)} identifier rows; no abstract text in processed outputs', flush=True)


# ---------------------------------------------------------------------------
# (b) Reporting audit replicates
# ---------------------------------------------------------------------------


def audit(n=200, tools=None, seconds=None):
    from census.build import build_reporting_audit as ba
    started = time.monotonic()
    reg = load_registry()
    ctx = f'({reg.context_query})'
    published = pd.read_csv(PROCESSED_DIR / f'reporting_audit_papers_{ba.YEAR}.csv', dtype=str)
    tools = tools or list(ba.TOOLS)
    for tool in tools:
        dest = RAW / 'audit' / f'{tool}.json'
        if dest.exists():
            continue
        if seconds and time.monotonic() - started >= seconds:
            break
        t = reg.by_id(tool)
        frame = ba.frame_pmcids(ba.frame_query(t, ctx))
        existing = sorted(published.query('tool_id == @tool').pmcid)
        census = len(frame) < 3 * n
        first = None if census else existing
        parts = draw_replicates(sorted(frame), n, first=first, seed=f'{SEED}-audit-{tool}', census=census)
        areg = ba.alias_re(t.aliases)
        receipts = []
        for rep, chosen in enumerate(parts, 1):
            res = list(ba.ThreadPoolExecutor(max_workers=4).map(
                lambda p, a=areg, tl=tool: ba.audit_paper(p, tl, a), chosen))
            receipts.append(dict(replicate=rep, rows=res))
        atomic_json(dest, dict(tool_id=tool, frame=len(frame), cap=n, census=census,
                               sizes=[len(p) for p in parts], receipts=receipts))
        print(f'audit {tool}: frame {len(frame)}, sizes {[len(p) for p in parts]}', flush=True)
    materialise_audit()


def _audit_rates(res, ba):
    ok = [r for r in res if r['scope'] != 'none']
    rec = dict(n=len(ok), analysed=len(ok), fetched=sum(r['fetched'] for r in res),
               in_methods_text=sum(r['scope'] == 'methods' for r in res))
    for ind in ('version', 'function', 'parameter', 'code'):
        k = sum(r[ind] for r in ok)
        lo, hi = ba.wilson(k, len(ok))
        rec.update({f'{ind}_n': k, f'{ind}_pct': 100 * k / len(ok) if ok else float('nan'),
                    f'{ind}_lo': 100 * lo, f'{ind}_hi': 100 * hi})
    k = sum(r['version'] and (r['function'] or r['parameter']) for r in ok)
    lo, hi = ba.wilson(k, len(ok))
    rec.update({'complete_n': k, 'complete_pct': 100 * k / len(ok) if ok else float('nan'),
                'complete_lo': 100 * lo, 'complete_hi': 100 * hi})
    k = sum(not (r['version'] or r['function'] or r['parameter']) for r in ok)
    rec.update({'name_only_n': k, 'name_only_pct': 100 * k / len(ok) if ok else float('nan')})
    return rec


def materialise_audit():
    from census.build import build_reporting_audit as ba
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((RAW / 'audit').glob('*.json'))
    if not files:
        return
    rows = []
    for path in files:
        obj = _read_json(path)
        for receipt in obj['receipts']:
            rec = _audit_rates(receipt['rows'], ba)
            rec.update(tool_id=obj['tool_id'], replicate=receipt['replicate'], frame=obj['frame'],
                       sampled=obj['sizes'][receipt['replicate'] - 1],
                       sampling='census-split' if obj['census'] else 'disjoint-srs')
            rows.append(rec)
    cols = ['tool_id', 'replicate', 'sampling', 'frame', 'sampled', 'fetched', 'analysed',
            'in_methods_text', 'version_n', 'version_pct', 'version_lo', 'version_hi',
            'function_n', 'function_pct', 'function_lo', 'function_hi',
            'parameter_n', 'parameter_pct', 'parameter_lo', 'parameter_hi',
            'code_n', 'code_pct', 'code_lo', 'code_hi',
            'complete_n', 'complete_pct', 'complete_lo', 'complete_hi', 'name_only_n', 'name_only_pct']
    df = pd.DataFrame(rows)[cols].sort_values(['tool_id', 'replicate'])
    df.to_csv(OUT / 'reporting_audit_replicates.csv', index=False)
    print(f'published {len(df)} reporting-audit replicate rows from {len(files)}/6 tools', flush=True)


# ---------------------------------------------------------------------------
# (c) Validation-set replicates
# ---------------------------------------------------------------------------


def _frame(name):
    path = DATA_DIR / 'validation' / 'frames' / f'{name}_frame.csv'
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _val_items(name):
    return pd.read_csv(DATA_DIR / 'validation' / f'{name}.csv', dtype=str, keep_default_na=False)


def _keyset(frame, cols):
    return [tuple(row[c] for c in cols) for _, row in frame.iterrows()]


def _draw_by_stratum(frame, sizes, seed, first_map=None):
    """Draw three disjoint replicates from each stratum, anchored to existing ids."""
    parts = [[], [], []]
    for stratum, g in frame.groupby('stratum', sort=True):
        n = sizes[stratum]
        first = None
        if first_map is not None:
            first = first_map.get(stratum, [])
        if first is not None and len(first) != n:
            raise ValueError(f'historical anchor for {stratum} has {len(first)} items, expected {n}')
        drawn = draw_replicates([dict(r) for _, r in g.iterrows()], n, first=first,
                                seed=f'{seed}-{stratum}', census=len(g) < 3 * n)
        for i in range(3):
            parts[i].extend(drawn[i])
    return parts


def _first_map(frame, label_df, join_cols, n_map):
    """Map historical label identifiers onto frame rows, per stratum."""
    out = {}
    for stratum, g in frame.groupby('stratum', sort=True):
        n = n_map[stratum]
        sub = label_df[label_df['stratum'] == stratum] if 'stratum' in label_df.columns else label_df
        out[stratum] = [dict(r) for _, r in g.iterrows() if len(out.get(stratum, [])) < n and _row_in(sub, r, join_cols)]
        # keep deterministic slice of exactly n
        out[stratum] = out[stratum][:n]
    return out


def _row_in(label_df, frame_row, cols):
    for _, lr in label_df.iterrows():
        if all(str(lr[c]) == str(frame_row[c]) for c in cols if c in label_df.columns):
            return True
    return False


VALIDATION_NAMES = {
    'cellpose': 'cellpose_workflow_2025',
    'alias': 'alias_precision_2025',
    'lexicon': 'dl_lexicon_2021_2025',
    'domains': 'domain_keywords_2021_2025',
    'reporting_audit': 'reporting_audit_patterns_2025',
}


def validation(sets=None, seconds=None):
    """Draw and document the validation replicates. No item is labelled here."""
    from census.build import build_reporting_audit as ba
    sets = sets or list(VALIDATION_NAMES)
    for command in sets:
        name = VALIDATION_NAMES[command]
        design_path = VAL_OUT / f'{name}_design.json'
        if design_path.exists():
            continue
        if command == 'cellpose':
            frame = _frame(name)
            n_map = {s: 40 for s in frame.stratum.unique()}
            labels = _val_items(name).rename(columns={})
            labels['stratum'] = 'cellpose'
            # Historical draw unrecorded: three fresh seeded draws (decision 2026-10-06).
            parts = _draw_by_stratum(frame, n_map, f'{SEED}-validation-{command}')
            columns = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
        elif command == 'alias':
            frame = _frame(name)
            n_map = {s: 10 for s in frame.stratum.unique()}
            labels = _val_items(name)
            labels['stratum'] = labels['tool_id']
            parts = _draw_by_stratum(frame, n_map, f'{SEED}-validation-{command}')
            columns = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
        elif command == 'lexicon':
            frame = _frame(name)
            n_map = {'lex_pos': 80, 'lex_neg': 120}
            labels = _val_items(name)
            parts = _draw_by_stratum(frame, n_map, f'{SEED}-validation-{command}')
            columns = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
        elif command == 'domains':
            frame = _frame(name)
            n_map = {s: 8 for s in frame.stratum.unique()}
            labels = _val_items(name)
            labels['stratum'] = labels['area']
            parts = _draw_by_stratum(frame, n_map, f'{SEED}-validation-{command}')
            columns = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
        else:  # reporting_audit pattern-validation sample
            papers = pd.read_csv(PROCESSED_DIR / 'reporting_audit_papers_2025.csv', dtype=str)
            papers = papers[papers['scope'] != 'none'].copy()
            papers['stratum'] = papers['tool_id']
            papers['epmc_id'] = ''
            papers['pmcid'] = papers['pmcid'].astype(str)
            papers['year'] = '2025'
            frame = papers[['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']].copy()
            n_map = {s: 10 for s in frame.stratum.unique()}
            labels = pd.concat([pd.read_csv(DATA_DIR / 'validation' / f, dtype=str)
                                for f in ('reporting_audit_labels_gemini.csv',)], ignore_index=True)
            labels['stratum'] = labels['item_id'].str.rsplit('-', n=1).str[0]
            labels['pmcid'] = labels['item_id'].str.rsplit('-', n=1).str[1]
            first = _anchor(frame, labels, ['stratum', 'pmcid'], n_map)
            parts = _draw_by_stratum(frame, n_map, f'{SEED}-validation-{command}', first)
            columns = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
        VAL_OUT.mkdir(parents=True, exist_ok=True)
        sizes = []
        for i, part in enumerate(parts, 1):
            d = pd.DataFrame(part)[columns]
            d.to_csv(VAL_OUT / f'{name}_items_r{i}.csv', index=False)
            sizes.append(len(d))
        _write_bundles(name, command, parts)
        _write_rubric(name, command)
        atomic_json(design_path, dict(name=name, command=command, seed=SEED, replicate_sizes=sizes,
                                      anchor=('reporting-audit seeded sample' if command not in ('cellpose', 'alias', 'lexicon', 'domains') else 'none: three fresh seeded draws'),
                                      note='Replicates are disjoint. Census thirds keep every frame record.'))
        print(f'validation {command}: {sizes} -> {VAL_OUT / (name + "_items_r1.csv")}', flush=True)


def _anchor(frame, labels, key_cols, n_map):
    """Deterministic historical anchor per stratum, in frame order, exactly n."""
    out = {}
    for stratum, g in frame.groupby('stratum', sort=True):
        n = n_map[stratum]
        sub = labels[labels.get('stratum') == stratum]
        wanted = {tuple(str(lr[c]) for c in key_cols) for _, lr in sub.iterrows()}
        keep = [dict(row) for _, row in g.iterrows()
                if tuple(str(row[c]) for c in key_cols) in wanted]
        if len(keep) < n:
            raise ValueError(f'{stratum}: historical anchor matched {len(keep)} of {n}')
        out[stratum] = keep[:n]
    return out


def _write_bundles(name, command, parts):
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    for i, part in enumerate(parts, 1):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as ex:
            lines = [json.dumps(b, ensure_ascii=False) for b in ex.map(lambda it: _bundle_item(command, it), part)]
        (ANN_DIR / f'{name}_r{i}.jsonl').write_text('\n'.join(lines) + '\n')


def _corpus_text():
    if not hasattr(_corpus_text, 'cache'):
        d = pd.read_csv(PROCESSED_DIR / 'random_sample_2021_2025.csv.gz', dtype={'epmc_id': str})
        _corpus_text.cache = {(str(r.tool_id), str(r.epmc_id)): (str(r.title), str(r.abstract)) for r in d.itertuples()}
    return _corpus_text.cache


def _fast_xml(pmcid):
    """Cached full text; two quick attempts, persistent errors recorded as unavailable."""
    from census.build import build_reporting_audit as ba
    import requests
    path = ba.XML_DIR / f'{pmcid}.xml'
    if path.exists():
        return path.read_text() or None
    for _ in range(2):
        try:
            r = ba._SESSION.get(ba.FULLTEXT.format(pmcid=pmcid), timeout=15)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            path.write_text(r.text)
            return r.text
        if r.status_code == 404:
            break
    path.write_text('')
    return None


def _xml_texts(pmcid, aliases):
    from census.build import build_reporting_audit as ba
    xml = _fast_xml(str(pmcid))
    if not xml:
        return None
    try:
        root = ba.ET.fromstring(xml)
    except ba.ET.ParseError:
        return None
    ba._strip_citations(root)
    areg = ba.alias_re(aliases)
    secs = ba.methods_sections(root)
    methods = ba.mention_windows([b for s in secs for b in ba._blocks(s)], areg)
    body = root.find('.//body')
    body_wins = ba.mention_windows(ba._blocks(body), areg) if body is not None else []
    return dict(methods_mentions=methods, body_windows=body_wins[:40],
                full_text=ba._text(root)[:12000])


def _bundle_item(command, item):
    if command == 'lexicon' or command == 'domains':
        title, abstract = _corpus_text().get((str(item['tool_id']), str(item['epmc_id'])), ('', ''))
        return dict(identifier=item.get('epmc_id') or item.get('pmcid'), tool_id=item['tool_id'],
                    year=item['year'], stratum=item['stratum'], title=title, abstract=abstract)
    if command == 'cellpose':
        aliases = ['Cellpose', 'ImageJ', 'Fiji', 'ImageJ2', 'FIJI']
        return dict(identifier=item['pmcid'], tool_id='cellpose', year=item['year'],
                    stratum=item['stratum'], texts=_xml_texts(item['pmcid'], aliases))
    if command == 'alias':
        reg = load_registry()
        aliases = reg.by_id(item['tool_id']).aliases
        return dict(identifier=item['pmcid'], tool_id=item['tool_id'], year=item['year'],
                    stratum=item['stratum'], texts=_xml_texts(item['pmcid'], aliases))
    # reporting_audit pattern validation
    from census.validation import validate_reporting_audit as va
    import json as _json
    wins = {}
    for line in open(RAW_DIR / 'reporting_audit' / 'windows_2025.jsonl'):
        r = _json.loads(line)
        wins[(r['pmcid'], r['tool_id'])] = r['windows']
    return dict(item_id=f"{item['tool_id']}-{item['pmcid']}", tool_id=item['tool_id'],
                pmcid=item['pmcid'], methods_mentions=wins.get((item['pmcid'], item['tool_id']), []),
                code_context=va.code_context(item['pmcid']))


RUBRIC_HEADER = {
    'cellpose': ('How was Cellpose used in this paper?', 'Cellpose workflow sample'),
    'alias': ('Does the tool name refer to the named software, and was it used for image acquisition or analysis?', 'Alias precision sample'),
    'lexicon': ('Does the title and abstract report a deep-learning method?', 'Deep-learning lexicon sample'),
    'domains': ('Does the matched keyword indicate the research area in this title and abstract?', 'Research-area keyword sample'),
    'reporting_audit': ('Does the paper report each of the four indicators (version, function, parameter, code) for this tool?', 'Reporting-audit pattern sample'),
}


def _write_rubric(name, command):
    question, title = RUBRIC_HEADER[command]
    rows = []
    if command == 'cellpose':
        labels = _val_items(name)
        allowed = sorted(labels['workflow'].unique())
    elif command == 'alias':
        labels = _val_items(name)
        allowed = sorted(labels['sense'].unique()) + sorted(labels['use'].unique())
    elif command == 'lexicon':
        labels = _val_items(name)
        allowed = sorted(labels['label'].unique())
    elif command == 'domains':
        labels = _val_items(name)
        allowed = sorted(labels['label'].unique())
    else:
        allowed = ['0', '1']
    lines = [f'# Rubric: {title}', '', '## Labelling question', '', question, '',
             '## Allowed labels', '', ', '.join(f'`{a}`' for a in allowed), '',
             '## Inputs', '', 'The annotation bundle gives the identifier, the tool and the text.',
             'For abstract-based sets that is the title and abstract; for full-text sets it is the',
             'Methods mention windows and a full-text excerpt around the tool name. No pattern or',
             'classifier result is shown.', '',
             '## Provenance', '', 'Reconstructed from the existing label files, `data/validation/README.md`',
             'and the manuscript Methods sections (Validation samples; Host-platform co-mentions and',
             'the Cellpose sample; Reporting audit). Two independent annotators label each replicate.', '',]
    (VAL_OUT / f'{name}_RUBRIC.md').write_text('\n'.join(lines) + '\n')


# ---------------------------------------------------------------------------
# (e) Deviation summary
# ---------------------------------------------------------------------------


def _deviation_rows():
    rows = []

    def add(sample, key, values, reported, lo, hi, note=''):
        vals = [v for v in values if v is not None]
        if not vals:
            rows.append(dict(sample=sample, key=key, r1=None, r2=None, r3=None, mean=None, sd=None,
                             min=None, max=None, reported=reported, reported_lo=lo, reported_hi=hi,
                             outside_interval='', note=note))
            return
        outside = ''
        if reported is not None and lo is not None and hi is not None:
            outside = any(v < lo or v > hi for v in vals)
        rows.append(dict(sample=sample, key=key, r1=values[0], r2=values[1], r3=values[2],
                         mean=sum(vals) / len(vals), sd=pd.Series(vals).std(ddof=1) if len(vals) > 1 else 0.0,
                         min=min(vals), max=max(vals), reported=reported, reported_lo=lo, reported_hi=hi,
                         outside_interval=str(bool(outside)), note=note))

    rep_path = OUT / 'dl_share_replicates.csv'
    if rep_path.exists():
        reps = pd.read_csv(rep_path)
        reported = pd.read_csv(PROCESSED_DIR / 'dl_estimates.csv')
        for _, r in reported.iterrows():
            g = reps[(reps.tool_id == r.tool_id) & (reps.year == r.year) & (reps.tool_id != 'field_core')]
            if len(g) != 3:
                continue
            g = g.sort_values('replicate')
            note = 'census-split thirds; union estimate has no sampling error' if (g.sampling == 'census-split').all() else ''
            add('abstract_dl_tool_year', f'{r.tool_id} {int(r.year)}', list(g.dl_share),
                float(r.dl_fraction), float(r.ci_lo), float(r.ci_hi), note)
        field = pd.read_csv(PROCESSED_DIR / 'dl_field_yearly.csv')
        fg = reps[reps.tool_id == 'field_core']
        for _, r in field.iterrows():
            g = fg[fg.year == r.year].sort_values('replicate')
            if len(g) != 3:
                continue
            add('abstract_dl_field', f'field {int(r.year)}', list(g.dl_share), float(r.dl_share),
                float(r.dl_share_lo), float(r.dl_share_hi))
        dom_path = OUT / 'domain_share_replicates.csv'
        enrichment = PROCESSED_DIR / 'domain_enrichment.csv'
        if dom_path.exists() and enrichment.exists():
            dom = pd.read_csv(dom_path)
            enr = pd.read_csv(enrichment)
            pooled = dom[dom.year == '2021-2025']
            for _, r in enr.iterrows():
                g = pooled[(pooled.tool_id == r.tool_id) & (pooled.domain == r.domain)].sort_values('replicate')
                if len(g) != 3:
                    continue
                add('abstract_domain_share', f'{r.tool_id} {r.domain}', list(g.share / 100.0),
                    float(r.share) / 100.0, None, None, 'bootstrap interval is on the ratio, not the share')
    audit_path = OUT / 'reporting_audit_replicates.csv'
    if audit_path.exists():
        reps = pd.read_csv(audit_path)
        rep = pd.read_csv(PROCESSED_DIR / 'reporting_audit_2025.csv')
        for _, r in rep.iterrows():
            g = reps[reps.tool_id == r.tool_id].sort_values('replicate')
            if len(g) != 3:
                continue
            note = 'census-split thirds' if (g.sampling == 'census-split').all() else ''
            for ind in ('version', 'function', 'parameter', 'code', 'complete', 'name_only'):
                add('reporting_audit', f'{r.tool_id} {ind}', list(g[f'{ind}_pct'] / 100.0),
                    float(r[f'{ind}_pct']) / 100.0,
                    float(r.get(f'{ind}_lo', float('nan'))) / 100.0 if not pd.isna(r.get(f'{ind}_lo', float('nan'))) else None,
                    float(r.get(f'{ind}_hi', float('nan'))) / 100.0 if not pd.isna(r.get(f'{ind}_hi', float('nan'))) else None,
                    note)
    # Validation spread across replicates uses agreed labels from both annotators:
    # see validation_replicates*.csv (label_replicates, label_round2) and validation_pooled_2025.csv.
    add('fiji_only_country_check', 'titles all bioimaging', [None, None, None], None, None, None,
        'historical draw of 40 titles; code, frame and seed not retained, not reproducible')
    return pd.DataFrame(rows)


def pool():
    """Rebuild pooled reporting-audit outputs from committed replicate data and labels."""
    from census.build import build_reporting_audit as ba
    reg = load_registry()
    summary = pd.read_csv(OUT / 'reporting_audit_replicates.csv')
    rows = []
    for tool_id in ba.TOOLS:
        group = summary[summary.tool_id == tool_id].sort_values('replicate')
        if group.empty:
            continue
        if group['replicate'].tolist() != [1, 2, 3]:
            raise ValueError(f'{tool_id}: expected three committed audit replicates')
        if group['frame'].nunique() != 1 or group['sampling'].nunique() != 1:
            raise ValueError(f'{tool_id}: inconsistent committed audit design')
        n = int(group['analysed'].sum())
        rec = dict(n=n, analysed=n, fetched=int(group['fetched'].sum()),
                   in_methods_text=int(group['in_methods_text'].sum()))
        for ind in ('version', 'function', 'parameter', 'code', 'complete'):
            k = int(group[f'{ind}_n'].sum())
            lo, hi = ba.wilson(k, n)
            rec.update({f'{ind}_n': k, f'{ind}_pct': 100 * k / n if n else float('nan'),
                        f'{ind}_lo': 100 * lo, f'{ind}_hi': 100 * hi})
        name_only = int(group['name_only_n'].sum())
        rec.update(name_only_n=name_only,
                   name_only_pct=100 * name_only / n if n else float('nan'))
        tool = reg.by_id(tool_id)
        rec.update(tool_id=tool_id, name=tool.name, year=ba.YEAR,
                   frame=int(group['frame'].iloc[0]), sampled=int(group['sampled'].sum()),
                   replicates=3, census=group['sampling'].iloc[0] == 'census-split')
        rows.append(rec)
    order = list(ba.TOOLS)
    out = pd.DataFrame(rows).set_index('tool_id').loc[[t for t in order if t in {r['tool_id'] for r in rows}]].reset_index()
    first = ['tool_id', 'name', 'year', 'frame', 'sampled', 'replicates', 'census']
    out = out[first + [c for c in out.columns if c not in first]]
    dest = PROCESSED_DIR / f'reporting_audit_pooled_{ba.YEAR}.csv'
    out.to_csv(dest, index=False)
    print(f'wrote {dest.name}: {len(out)} tools')
    # pattern validation over the three replicates
    papers = pd.read_csv(PROCESSED_DIR / f'reporting_audit_papers_{ba.YEAR}.csv')
    papers['item_id'] = papers['tool_id'] + '-' + papers['pmcid']
    pat = papers.set_index('item_id')
    pairs = [(DATA_DIR / 'validation' / 'reporting_audit_labels_syn.csv',
              DATA_DIR / 'validation' / 'reporting_audit_labels_gemini.csv')]
    for rep in (2, 3):
        pairs.append((VAL_OUT / f'reporting_audit_patterns_2025_labels_syn_r{rep}.csv',
                      VAL_OUT / f'reporting_audit_patterns_2025_labels_gemini_r{rep}.csv'))
    vrows = []
    for ind in ('version', 'function', 'parameter', 'code'):
        tp = fp = fn = items = agreed = 0
        agree_pct = []
        for f1, f2 in pairs:
            a = pd.read_csv(f1, dtype=str).set_index('item_id')[ind].astype(int)
            b = pd.read_csv(f2, dtype=str).set_index('item_id')[ind].astype(int)
            common = a.index.intersection(b.index).intersection(pat.index)
            a, b = a.loc[common], b.loc[common]
            agree_pct.append(100 * (a == b).mean())
            ref = a[a == b]
            p = pat.loc[ref.index, ind].astype(int)
            items += len(common)
            agreed += len(ref)
            tp += int(((p == 1) & (ref == 1)).sum())
            fp += int(((p == 1) & (ref == 0)).sum())
            fn += int(((p == 0) & (ref == 1)).sum())
        vrows.append(dict(indicator=ind, items=items, consensus_items=agreed,
                          annotator_agreement_min_pct=round(min(agree_pct), 1),
                          annotator_agreement_max_pct=round(max(agree_pct), 1),
                          pattern_tp=tp, pattern_fp=fp, pattern_fn=fn,
                          precision_pct=round(100 * tp / (tp + fp), 1) if tp + fp else None,
                          recall_pct=round(100 * tp / (tp + fn), 1) if tp + fn else None))
    v = pd.DataFrame(vrows)
    v.to_csv(PROCESSED_DIR / f'reporting_audit_validation_pooled_{ba.YEAR}.csv', index=False)
    print(v.to_string(index=False))
    return out


def summarise():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _deviation_rows()
    dest = OUT / 'deviation_summary.csv'
    rows.to_csv(dest, index=False)
    print(f'wrote {len(rows)} deviation rows to {dest}')
    return rows


# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('draw', 'abstracts', 'audit', 'validation', 'pool', 'summarise'):
        p = sub.add_parser(name)
        if name in ('draw', 'abstracts'):
            p.add_argument('--tools', nargs='+')
            p.add_argument('--years', nargs='+', type=int)
            p.add_argument('--seed', default=SEED)
        if name == 'abstracts':
            p.add_argument('--seconds', type=float)
            p.add_argument('--max-jobs', type=int)
        if name == 'audit':
            p.add_argument('--tools', nargs='+')
            p.add_argument('--n', type=int, default=200)
            p.add_argument('--seconds', type=float)
        if name == 'validation':
            p.add_argument('--sets', nargs='+')
            p.add_argument('--seconds', type=float)
    args = vars(ap.parse_args(argv))
    command = args.pop('command')
    globals()[command](**args)


if __name__ == '__main__':
    main()
