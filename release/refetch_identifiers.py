#!/usr/bin/env python3
"""Locally refetch the archived sampled articles by exact Europe PMC identifiers.

This is an optional reproduction step, never called by the offline builder.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-network', action='store_true', help='explicitly allow Europe PMC downloads')
    args = parser.parse_args()
    if not args.allow_network:
        parser.error('refetching requires --allow-network; no data are uploaded')
    if args.output.exists():
        parser.error('refusing to overwrite output')
    root = Path(__file__).resolve().parents[1]
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    from census.sources.europepmc import _fetch_records
    sampled = args.archive / 'data/processed/random_sample_2021_2025_ids.csv'
    with sampled.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        columns, rows = list(reader.fieldnames), list(reader)
    lookup = {}
    for frame in sorted((args.archive / 'data/sampling_frames/tool_year').glob('*.csv')):
        tool, year = frame.stem.rsplit('_', 1)
        with frame.open(newline='', encoding='utf-8') as stream:
            for item in csv.DictReader(stream):
                lookup.setdefault((tool, year, item['id']), set()).add(item['source'])
    pairs = []
    for row in rows:
        key = (row['tool_id'], row['year'], row['epmc_id'])
        sources = lookup.get(key, set())
        if len(sources) != 1 or not next(iter(sources), ''):
            raise ValueError(f'missing or ambiguous Europe PMC source for {key}')
        pairs.append((row['epmc_id'], next(iter(sources))))
    records = _fetch_records(list(dict.fromkeys(pairs)))
    records = {(r['id'], r['source']): r for r in records}
    missing = [p for p in pairs if p not in records]
    if missing:
        raise ValueError(f'{len(missing)} archived identifiers no longer returned; first: {missing[:5]}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, 'wt', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, columns + ['title', 'abstract'], lineterminator='\n')
        writer.writeheader()
        for row, pair in zip(rows, pairs):
            record = records[pair]
            writer.writerow({**row, 'title': record.get('title') or '',
                             'abstract': record.get('abstractText') or ''})
    print(f'Refetched {len(records)} unique records into {len(rows)} tool-paper rows: {args.output}')


if __name__ == '__main__':
    main()
