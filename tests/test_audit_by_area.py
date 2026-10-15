"""Check audit inclusion, metadata-only vocabulary and direct risk differences."""
import json

import pandas as pd
import pytest

from census.validation import audit_by_area as area


def test_receipts_metadata_and_missing_text(tmp_path):
    audit = tmp_path / 'audit'
    xml = tmp_path / 'xml'
    audit.mkdir()
    xml.mkdir()
    def row(pmcid, **kwargs):
        return dict(pmcid=pmcid, scope='methods', version=False,
                    function=False, parameter=False, **kwargs)
    receipts = [dict(replicate=1, rows=[row('PMC1')]),
                dict(replicate=2, rows=[row('PMC2', code=True)]),
                dict(replicate=3, rows=[row('PMC3'), dict(row('PMC4'), scope='none')])]
    (audit / 'imagej.json').write_text(json.dumps(dict(tool_id='imagej', receipts=receipts)))
    (xml / 'PMC1.xml').write_text('<article xmlns="urn:jats"><front><article-meta>'
        '<title-group><article-title>Cell <italic>segmentation</italic></article-title></title-group>'
        '<abstract><p>A study</p></abstract></article-meta></front></article>')
    (xml / 'PMC2.xml').write_text('<article><front><article-meta><title-group>'
        '<article-title>Cell biology</article-title></title-group><abstract><p>Cells</p></abstract>'
        '</article-meta></front><back><ref-list><article-title>Software</article-title>'
        '</ref-list></back></article>')
    d = area.load_records(audit, xml)
    assert len(d) == 4
    assert not d.set_index('pmcid').loc['PMC4', 'analysed']
    assert d.set_index('pmcid').loc['PMC1', 'methods_vocabulary'] == True
    assert d.set_index('pmcid').loc['PMC2', 'methods_vocabulary'] == False
    assert pd.isna(d.set_index('pmcid').loc['PMC3', 'methods_vocabulary'])
    s = area.summarise(d).iloc[0]
    assert s['n'] == 3
    assert s['name_only_n'] == 3  # code alone does not change name-only status
    assert s['missing_text_n'] == 2
    assert s['sampled_n'] == 4
    assert s['excluded_n'] == 1
    assert s['vocabulary_pct'] == 50  # unavailable text is not a negative flag
    assert s['without_vocabulary_n'] == s['with_vocabulary_n'] == 1
    (xml / 'PMC3.xml').write_text('<broken')
    assert area.load_records(audit, xml).missing_text.sum() == 2


def test_direct_mantel_haenszel_risk_difference():
    d = pd.DataFrame([
        ('imagej', False, True), ('imagej', False, True), ('imagej', False, False),
        ('qupath', False, False), ('imagej', True, False),
        ('qupath', True, True), ('qupath', True, False), ('qupath', True, False),
    ], columns=['tool_id', 'methods_vocabulary', 'name_only'])
    g = area.gaps(d).iloc[0]
    assert g.raw_gap_pp == pytest.approx(25)
    assert g.stratified_gap_pp == pytest.approx(100 / 6)
    d['missing_text'] = False
    s = area.summarise(d).set_index('tool_id')
    assert s.loc['imagej', 'without_vocabulary_name_only_pct'] == pytest.approx(200 / 3)
    assert s.loc['qupath', 'with_vocabulary_name_only_n'] == 1
    d['methods_vocabulary'] = pd.NA
    assert pd.isna(area.gaps(d).iloc[0].stratified_gap_pp)


def test_pool_runs_area_audit_after_pooled_inputs(monkeypatch):
    from census import run_all
    calls = []
    monkeypatch.setattr('sys.argv', ['run_all.py', '--pool'])
    monkeypatch.setattr(run_all.subprocess, 'run', lambda cmd, **kw: calls.append(cmd))
    run_all.main()
    assert calls[-1][1:] == ['-m', 'census.validation.audit_by_area']
    assert calls[0][1:] == ['-m', 'census.validation.replicates', 'pool']


def test_pooled_shares_match_published():
    if not any((area.RAW_DIR / 'replicates' / 'audit').glob('*.json')):
        pytest.skip('Raw audit records data/raw/replicates/audit/*.json are not shipped')
    d = area.load_records()
    got = area.summarise(d).set_index('tool_id')
    published = pd.read_csv(area.PROCESSED_DIR / 'reporting_audit_pooled_2025.csv').set_index('tool_id')
    for tool, row in published.iterrows():
        assert got.loc[tool, 'n'] == row.analysed
        assert got.loc[tool, 'name_only_n'] == row.name_only_n
        assert got.loc[tool, 'name_only_pct'] == pytest.approx(row.name_only_pct)
