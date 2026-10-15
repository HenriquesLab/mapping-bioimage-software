"""Keep the public walkthroughs complete and their offline renderer inputs usable."""
import json
from pathlib import Path
import re

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from census.tables.make_si_tables import TABLES

ROOT = Path(__file__).resolve().parents[1]
FIGURES = [
    'Figure1__overview', 'Figure2__landscape', 'Figure3__citations',
    'Figure4__reach', 'Figure5__domains', 'Figure6__deep_learning',
    'SFigure1__trajectories', 'SFigure2__terms', 'SFigure3__triangulation',
]


def notebooks():
    return {p.stem: json.loads(p.read_text()) for p in (ROOT / 'notebooks').glob('*.ipynb')}


def sources(nb):
    return '\n'.join(''.join(c['source']) for c in nb['cells'])


def test_every_publication_output_has_a_mapped_walkthrough():
    readme = (ROOT / 'notebooks/README.md').read_text()
    content = '\n'.join(map(sources, notebooks().values()))
    figures = set(FIGURES)
    manuscript = ROOT.parent / 'MANUSCRIPT'
    if manuscript.is_dir():
        figures.update(p.stem for pattern in ('Figure*.png', 'SFigure*.png')
                       for p in (manuscript / 'FIGURES').glob(pattern))
        si = manuscript / '02_SUPPLEMENTARY_INFO.md'
        table_names = set(re.findall(r'<!-- TABLE:(\w+) START -->', si.read_text()))
        assert table_names == set(TABLES)
    for target in sorted(figures | set(TABLES)):
        assert target in readme, f'{target}: missing coverage map entry'
        assert target in content, f'{target}: missing notebook coverage'
    assert len(notebooks()) == 10


def test_walkthroughs_document_inputs_rebuilding_and_checks():
    for name, nb in notebooks().items():
        assert nb['cells'][0]['cell_type'] == 'markdown', name
        text = sources(nb)
        assert '## Inputs' in text, name
        assert '## Rebuilding from scratch' in text, name
        assert 'release/refetch_identifiers.py' in text, name
        assert nb['cells'][-1]['cell_type'] == 'code', name
        assert 'assert' in ''.join(nb['cells'][-1]['source']), name
        for i, cell in enumerate(nb['cells']):
            if cell['cell_type'] == 'code':
                assert i and nb['cells'][i - 1]['cell_type'] == 'markdown', (name, i)
        assert not any(c['cell_type'] == 'code' and any(
            o.get('output_type') == 'error' for o in c.get('outputs', [])) for c in nb['cells']), name


def test_term_renderer_accepts_aggregates_without_loading_corpus(monkeypatch):
    from census.figures import sfig2_terms as figure
    def no_corpus():
        pytest.fail('The aggregate renderer tried to load article text')
    monkeypatch.setattr(figure.dm, 'load_corpus', no_corpus)
    rows = pd.DataFrame([dict(tool_id=t, word='neuron', tool_pct=20., base_pct=10., z=2.)
                         for t in figure.TOOLS])
    fig = figure.build_figure(terms=rows)
    try:
        assert len(fig.axes) == 8
        for ax in fig.axes:
            assert ax.get_yticklabels()[0].get_text() == 'neuron'
            assert ax.collections[-1].get_offsets()[0, 0] == 20.
    finally:
        plt.close(fig)


def test_citation_renderer_accepts_years_without_api_lookup(monkeypatch):
    from census.build import build_citations
    from census.figures import fig3_citations as figure
    def no_api():
        pytest.fail('The offline renderer tried to look up paper years')
    monkeypatch.setattr(build_citations, 'first_paper_year', no_api)
    years = {t: 2019 for t in figure.table().index}
    yearly = figure.yearly(first_years=years)
    assert yearly.year.min() >= 2020
    assert not yearly.empty
    fig = figure.build_figure(first_years=years)
    try:
        assert len(fig.axes) == 2
    finally:
        plt.close(fig)
