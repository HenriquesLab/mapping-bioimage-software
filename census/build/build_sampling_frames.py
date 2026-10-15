#!/usr/bin/env python3
"""Rebuild identifier-only sampling frames offline from the existing API caches.

Cached response order and historical incomplete frames remain unchanged.
Run with ``python -m census.build.build_sampling_frames`` from the repository root.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, columns: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, columns, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def cache_frame(query: str, kind: str, cache: Path) -> tuple[list[dict], dict]:
    """Match _http._cache_path and cursor traversal without importing HTTP code."""
    cursor, seen, rows, pages = '*', set(), [], []
    expected, reason = None, ''
    while cursor:
        if cursor in seen:
            reason = 'cursor cycle'
            break
        seen.add(cursor)
        params = dict(query=query, format='json', resultType=kind,
                      pageSize=1000, cursorMark=cursor)
        key = API + '?' + json.dumps(params, sort_keys=True)
        path = cache / (hashlib.sha256(key.encode()).hexdigest()[:20] + '.json')
        if not path.exists():
            reason = f'missing cache page {path.name}'
            break
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            reason = f'unreadable cache page {path.name}: {exc}'
            break
        pages.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=digest(path)))
        if expected is None:
            expected = int(data['hitCount']) if 'hitCount' in data else None
        result = (data.get('resultList') or {}).get('result', [])
        rows.extend(result)
        nxt = data.get('nextCursorMark')
        if not result or not nxt or nxt == cursor:
            break
        cursor = nxt
    if not reason and expected is not None and len(rows) != expected:
        reason = f'cached hitCount {expected}, recovered {len(rows)} records'
    return rows, dict(query=query, result_type=kind, cached_hit_count=expected,
                      recovered_records=len(rows), complete=not reason,
                      issue=reason, cache_pages=pages)


def relative_paths(value):
    """Keep validation provenance portable without changing its identifier fields."""
    if isinstance(value, dict):
        return {key: relative_paths(child) for key, child in value.items()}
    if isinstance(value, list):
        return [relative_paths(child) for child in value]
    if isinstance(value, str) and value.startswith(str(ROOT) + '/'):
        return value[len(str(ROOT)) + 1:].replace('data/raw/validation_frames/', 'data/sampling_frames/validation/').replace('data/validation/frames/', 'data/sampling_frames/validation/')
    return value


def build(dest: Path = ROOT) -> dict:
    """Write frozen frames under dest/data/sampling_frames and return provenance."""
    report = dict(sampling_frames=[], missing_frames=[])
    corpus_ids = ROOT / 'data/processed/random_sample_2021_2025_ids.csv'
    corpus_rows = read_csv(corpus_ids)[1] if corpus_ids.exists() else []
    frames_dir = ROOT / 'data/validation/frames'
    if not frames_dir.exists():
        frames_dir = ROOT / 'data/raw/validation_frames'
    for src in sorted(frames_dir.glob('*.csv')):
        columns, rows = read_csv(src)
        keep = [c for c in columns if c in {'stratum', 'tool_id', 'year', 'epmc_id', 'pmcid', 'id', 'source'}]
        write_csv(dest / 'data/sampling_frames/validation' / src.name, keep, rows)
    # Sidecars already contain identifier provenance, with no article text.
    for src in sorted(frames_dir.glob('*.json')):
        value = json.loads(src.read_text(encoding='utf-8'))
        write_json(dest / 'data/sampling_frames/validation' / src.name, relative_paths(value))
    # Existing registry helpers do not perform network I/O. Suppress bytecode writes.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    from census._registry import build_boolean_query, load_registry
    reg = load_registry()
    _, estimates = read_csv(ROOT / 'data/processed/dl_estimates.csv')
    # All registry tool-years includes zero-result censuses as well as actual samples.
    tool_years = {(t.id, y) for t in reg.tools for y in reg.years}
    tool_years.update((r['tool_id'], int(r['year'])) for r in estimates + corpus_rows)
    cache = ROOT / 'data/raw/europepmc'
    for tool, year in sorted(tool_years):
        query = f'{build_boolean_query(reg.by_id(tool), reg.context_query)} AND PUB_YEAR:{year}'
        rows, info = cache_frame(query, 'idlist', cache)
        relative = f'data/sampling_frames/tool_year/{tool}_{year}.csv'
        write_csv(dest / relative, ['id', 'source'],
                  [dict(id=r.get('id', ''), source=r.get('source', '')) for r in rows])
        info.update(path=relative, tool_id=tool, year=year, identifiers=len(rows))
        if any(not r.get('id') or not r.get('source') for r in rows):
            info.update(complete=False, issue='identifier or source missing in cached response')
        report['sampling_frames'].append(info)

    _, audits = read_csv(ROOT / 'data/processed/reporting_audit_2025.csv')
    for row in audits:
        tool, year = row['tool_id'], int(row['year'])
        methods = ' OR '.join(reg.by_id(tool).terms('METHODS:'))
        query = f'({methods}) AND ({reg.context_query}) AND OPEN_ACCESS:Y AND PUB_YEAR:{year}'
        rows, info = cache_frame(query, 'lite', cache)
        ids = sorted({r['pmcid'] for r in rows if r.get('pmcid')})
        relative = f'data/sampling_frames/reporting_audit/{tool}_{year}.csv'
        write_csv(dest / relative, ['pmcid'], [dict(pmcid=i) for i in ids])
        info.update(path=relative, tool_id=tool, year=year, identifiers=len(ids),
                    archived_frame_count=int(row['frame']))
        if len(ids) != int(row['frame']):
            info.update(complete=False, issue=(info['issue'] + '; ' if info['issue'] else '')
                        + f'archived audit frame {row["frame"]}, recovered {len(ids)} PMCIDs')
        report['sampling_frames'].append(info)
    report['missing_frames'] = [dict(path=f['path'], issue=f['issue'])
                                for f in report['sampling_frames'] if not f['complete']]
    for row in estimates:
        frame = next(f for f in report['sampling_frames']
                     if f['path'] == f'data/sampling_frames/tool_year/{row["tool_id"]}_{row["year"]}.csv')
        if frame['identifiers'] != int(row['population']):
            report.setdefault('population_drift', []).append(dict(path=frame['path'],
                archived_population=int(row['population']), recovered_population=frame['identifiers']))

    folder = dest / 'data/sampling_frames'
    write_json(folder / 'metadata.json', report)
    lines = ['# Frozen sampling frames', '',
             'Identifier-only outputs of `python -m census.build.build_sampling_frames`.',
             'Tool-year frames preserve cached response order; audit PMCIDs are sorted and unique.',
             'Validation frames retain identifiers, strata and portable source metadata.',
             'No network requests are made. `metadata.json` records queries, cache checksums,',
             'population drift and completeness. Incomplete frames limit exact reproduction.', '',
             '## Known incomplete frames', '']
    lines += [f'- `{row["path"]}`: {row["issue"]}' for row in report['missing_frames']]
    (folder / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT, help='repository output root')
    args = parser.parse_args()
    report = build(args.output)
    print(f"Wrote {len(report['sampling_frames'])} cached frames; {len(report['missing_frames'])} incomplete")


if __name__ == '__main__':
    main()
