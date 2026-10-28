"""Frozen frames preserve archived identifiers when a complete local cache is available."""
import importlib
from pathlib import Path
import pytest


def test_sampling_frames_match_previous_archive(tmp_path):
    assert importlib.util.find_spec('census.build.build_sampling_frames') is not None
    frames = importlib.import_module('census.build.build_sampling_frames')
    cache = frames.ROOT / 'data/raw/europepmc'
    # the folder can exist empty (the HTTP helper creates it), so look for cached pages
    if not cache.is_dir() or not any(cache.rglob('*.json')):
        pytest.skip('Frame rebuild comparison requires local API caches')
    report = frames.build(tmp_path)
    missing = report['missing_frames']
    generated = tmp_path / 'data/sampling_frames'
    for tool in ('imagepro', 'nihimage', 'photoshop'):
        assert (generated / 'tool_year' / f'{tool}_2025.csv').is_file()
    # A partial cache cannot reproduce archived identifiers; exact missing-page counts
    # change as the registry grows and Europe PMC adds records.
    if any('missing cache page' in item['issue'] for item in missing):
        pytest.skip('Frame rebuild comparison requires the full local API cache')
    baseline = frames.ROOT / 'release/build/mapping-bioimage-software-2026.10.20/data/sampling_frames'
    if baseline.exists():
        old = {p.relative_to(baseline): p.read_bytes() for p in baseline.rglob('*')
               if p.is_file() and p.relative_to(baseline).as_posix() not in {'metadata.json', 'README.md'}}
        new = {p.relative_to(generated): p.read_bytes() for p in generated.rglob('*')
               if p.is_file() and p.relative_to(generated).as_posix() not in {'metadata.json', 'README.md'}}
        assert old.keys() <= new.keys()
        # Europe PMC adds and revises records after the archive was cut, so a refreshed cache
        # drifts by a few identifiers per frame; each frame must still overlap the archive by 90%.
        for name, contents in old.items():
            if name.suffix != '.csv':
                assert new[name] == contents
                continue
            before, after = set(contents.splitlines()), set(new[name].splitlines())
            assert len(before - after) <= max(5, 0.1 * len(before)), name
    assert (generated / 'README.md').is_file()


def test_cache_paging_reports_missing_then_recovers_order(tmp_path, monkeypatch):
    import hashlib
    import json
    from census.build import build_sampling_frames as frames

    monkeypatch.setattr(frames, 'ROOT', tmp_path)
    cache = tmp_path / 'cache'
    cache.mkdir()

    def page(cursor, data):
        params = dict(query='test', format='json', resultType='idlist', pageSize=1000, cursorMark=cursor)
        key = frames.API + '?' + json.dumps(params, sort_keys=True)
        (cache / (hashlib.sha256(key.encode()).hexdigest()[:20] + '.json')).write_text(json.dumps(data))

    page('*', {'hitCount': 2, 'nextCursorMark': 'next', 'resultList': {'result': [{'id': '2', 'source': 'MED'}]}})
    rows, info = frames.cache_frame('test', 'idlist', cache)
    assert [row['id'] for row in rows] == ['2']
    assert not info['complete'] and 'missing cache page' in info['issue']
    page('next', {'hitCount': 2, 'nextCursorMark': 'next', 'resultList': {'result': [{'id': '1', 'source': 'MED'}]}})
    rows, info = frames.cache_frame('test', 'idlist', cache)
    assert [row['id'] for row in rows] == ['2', '1']
    assert info['complete'] and len(info['cache_pages']) == 2
