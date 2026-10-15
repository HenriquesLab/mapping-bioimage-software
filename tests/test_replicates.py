"""Tests for disjoint replicate designs, with no network access."""
import random
import pytest


def draw(*args, **kwargs):
    from census.validation.replicates import draw_replicates
    return draw_replicates(*args, **kwargs)


def test_disjoint_equal_sizes_and_preserved_first():
    frame = list(range(100))
    first = random.Random('historical').sample(frame, 10)
    parts = draw(frame, 10, first=first, seed='recorded')
    assert parts[0] == first
    assert [len(p) for p in parts] == [10, 10, 10]
    assert len(set(sum(parts, []))) == 30


def test_seed_reproducibility_and_order_independence():
    a = draw(list(range(100)), 10, seed='recorded')
    assert a == draw(list(reversed(range(100))), 10, seed='recorded')
    assert a != draw(list(range(100)), 10, seed='different')


@pytest.mark.parametrize('population', [0, 1, 2, 12, 14, 517, 244, 179])
def test_census_split_keeps_every_record_balanced(population):
    frame = list(range(population))
    parts = draw(frame, max(5, population // 2), seed='census-seed')
    assert sorted(sum(parts, [])) == frame
    sizes = [len(p) for p in parts]
    assert max(sizes) - min(sizes) <= 1
    assert parts == draw(frame, max(5, population // 2), seed='census-seed')


def test_reject_duplicate_frame_and_invalid_first():
    with pytest.raises(ValueError):
        draw([1, 1, 2], 1)
    with pytest.raises(ValueError):
        draw(list(range(30)), 5, first=[999] * 5)
    with pytest.raises(ValueError):
        draw(list(range(30)), -1)


def test_cli_replicates_never_runs_original_builders(monkeypatch):
    from census import run_all
    calls = []
    monkeypatch.setattr('sys.argv', ['run_all.py', '--replicates', '--no-figures'])
    monkeypatch.setattr(run_all.subprocess, 'run', lambda cmd, **kw: calls.append(cmd))
    run_all.main()
    assert [cmd[3] for cmd in calls] == ['draw', 'abstracts', 'audit', 'validation', 'summarise']
    assert all(cmd[1:3] == ['-m', 'census.validation.replicates'] for cmd in calls)


def test_source_replicate_preserves_first_and_disjoint(monkeypatch):
    from census.sources import europepmc
    from census._registry import load_registry
    frame = [(str(i), 'MED') for i in range(100)]
    monkeypatch.setattr(europepmc, '_id_list', lambda q: frame)
    monkeypatch.setattr(europepmc, '_fetch_records', lambda ids: [{'id': i, 'source': s, 'title': '', 'abstractText': ''} for i, s in ids])
    reg = load_registry()
    t = reg.by_id('imagej')
    original, _ = europepmc.random_sample_works(t, reg, 2025, max_records=10, census_max=0)
    parts = [europepmc.random_sample_works(t, reg, 2025, max_records=10, census_max=0, replicate=r)[0] for r in (1, 2, 3)]
    assert parts[0] == original
    assert len({w['epmc_id'] for p in parts for w in p}) == 30


def test_dictionary_units():
    rows = [{'id': str(i), 'tool': 'x'} for i in range(30)]
    parts = draw(rows, 5, first=rows[:5], seed='dictionary')
    assert parts[0] == rows[:5]
    assert len({r['id'] for p in parts for r in p}) == 15


def test_source_census_replicates_partition_the_complete_frame(monkeypatch):
    from census.sources import europepmc
    from census._registry import load_registry
    frame = [(str(i), 'MED') for i in range(14)]
    monkeypatch.setattr(europepmc, '_id_list', lambda q: frame)
    monkeypatch.setattr(europepmc, '_fetch_records', lambda ids: [
        {'id': i, 'source': s, 'title': '', 'abstractText': ''} for i, s in ids])
    reg = load_registry()
    tool = reg.by_id('imagej')
    parts = [europepmc.random_sample_works(tool, reg, 2025, max_records=5,
             census_max=100, replicate=r)[0] for r in (1, 2, 3)]
    ids = [[row['epmc_id'] for row in part] for part in parts]
    assert sorted(int(i) for i in sum(ids, [])) == list(range(14))
    assert sorted(len(part) for part in ids) == [4, 5, 5]


def test_all_replicate_subcommands_are_implemented():
    from census.validation import replicates
    for name in ('draw', 'abstracts', 'audit', 'validation', 'summarise'):
        assert callable(getattr(replicates, name, None)), name

def test_census_flag_force_splits_balanced_thirds():
    """census=True keeps every record even when the frame could allow disjoint SRS."""
    frame = list(range(30))
    parts = draw(frame, 5, seed='forced', census=True)
    assert sorted(sum(parts, [])) == frame
    assert sorted(len(p) for p in parts) == [10, 10, 10]


def test_validation_draw_by_stratum_is_disjoint_and_equal():
    import pandas as pd
    from census.validation.replicates import _draw_by_stratum
    frame = pd.DataFrame([{'stratum': 'a', 'id': i} for i in range(50)]
                         + [{'stratum': 'b', 'id': i} for i in range(7)])
    sizes = {'a': 10, 'b': 3}
    parts = _draw_by_stratum(frame, sizes, 'val-seed')
    keys = [[(r['stratum'], r['id']) for r in p] for p in parts]
    flat = [k for p in keys for k in p]
    # Disjoint within each stratum: no unit repeats across replicates.
    assert len(flat) == len(set(flat))
    for p in keys:
        a = [k for k in p if k[0] == 'a']
        b = [k for k in p if k[0] == 'b']
        assert len(a) == 10  # 50 records allow three 10-record replicates
        assert len(b) in (2, 3)  # 7 records split into thirds of 3, 2, 2
    # b is the census branch: every record is retained across the three parts.
    assert sorted(k[1] for k in flat if k[0] == 'b') == list(range(7))

def test_source_disjoint_replicate_1_matches_historical(monkeypatch):
    from census.sources import europepmc
    from census._registry import load_registry
    import random as _random
    frame = [(str(i), 'MED') for i in range(500)]
    monkeypatch.setattr(europepmc, '_id_list', lambda q: frame)
    monkeypatch.setattr(europepmc, '_fetch_records', lambda ids: [
        {'id': i, 'source': s, 'title': '', 'abstractText': ''} for i, s in ids])
    reg = load_registry()
    tool = reg.by_id('imagej')
    original, _ = europepmc.random_sample_works(tool, reg, 2025, max_records=100, census_max=0)
    expected = _random.Random('20260929-imagej-2025').sample(frame, 100)
    assert [w['epmc_id'] for w in original] == [i for i, s in expected]
    parts = [europepmc.random_sample_works(tool, reg, 2025, max_records=100,
             census_max=0, replicate=r)[0] for r in (1, 2, 3)]
    assert [w['epmc_id'] for w in parts[0]] == [i for i, s in expected]
    assert len({w['epmc_id'] for p in parts for w in p}) == 300


def test_cli_replicate_hooks_do_not_call_original_builders(monkeypatch):
    import sys
    import runpy
    from census.build import build_reporting_audit as ba
    from census.validation import replicates
    calls = []
    monkeypatch.setattr(ba, 'main', lambda *a, **k: calls.append(('audit-main', a)))
    monkeypatch.setattr(ba, 'selftest', lambda: calls.append(('selftest',)))
    monkeypatch.setattr(replicates, 'audit', lambda **k: calls.append(('replicates-audit', k)))
    old = sys.argv
    sys.argv = ['build_reporting_audit.py', '--replicates']
    try:
        runpy.run_module('census.build.build_reporting_audit', run_name='__main__')
    except SystemExit:
        pass
    finally:
        sys.argv = old
    assert any(c[0] == 'replicates-audit' for c in calls)
    assert not any(c[0] == 'audit-main' for c in calls)
