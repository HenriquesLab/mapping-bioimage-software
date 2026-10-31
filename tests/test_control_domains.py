"""Microscope-control contrasts use the analysis corpus as their baseline."""
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt

from census._paths import PROCESSED_DIR
from census.figures import domains, fig5_domains

CONTROLS = {'zen', 'nis', 'lasx', 'cellsens', 'axiovision', 'metamorph'}


def test_control_enrichment_uses_analysis_baseline_and_preserves_analysis(tmp_path):
    if not (PROCESSED_DIR / 'random_sample_2021_2025.csv.gz').is_file():
        pytest.skip('Text corpus is not shipped; rebuild with release/refetch_identifiers.py')
    analysis_path = PROCESSED_DIR / 'domain_enrichment.csv'
    before = analysis_path.read_bytes()
    analysis = domains.load_corpus()
    expected = 100 * analysis[list(domains.DOMAINS)].mul(analysis.w, axis=0).sum() / analysis.w.sum()
    output = tmp_path / 'control.csv'
    result = domains.build_control_enrichment(output, n_boot=2, seed=1)
    assert set(result.tool_id) == CONTROLS
    assert list(result.columns) == list(pd.read_csv(analysis_path).columns)
    for _, rows in result.groupby('tool_id'):
        np.testing.assert_allclose(rows.set_index('domain').baseline.loc[expected.index], expected, rtol=1e-12)
    pd.testing.assert_frame_equal(pd.read_csv(output), result)
    assert analysis_path.read_bytes() == before


def test_stored_control_rows_and_baselines():
    result = pd.read_csv(PROCESSED_DIR / 'domain_enrichment_control.csv')
    assert set(result.tool_id) == CONTROLS
    assert not result.duplicated(['tool_id', 'domain']).any()
    assert (result.n >= domains.MIN_PAPERS).all()
    for _, rows in result.groupby('domain'):
        np.testing.assert_allclose(rows.baseline, rows.baseline.iloc[0], rtol=1e-12)
    assert result.groupby('tool_id').size().eq(len(domains.DOMAINS)).all()


def test_figure5_control_block_labels_and_gap():
    fig = fig5_domains.build_figure()
    try:
        ax = fig.axes[0]
        ticks = dict(zip([t.get_text() for t in ax.get_yticklabels()], ax.get_yticks()))
        names = ['ZEN', 'NIS-Elements', 'LAS X', 'cellSens', 'AxioVision', 'MetaMorph']
        assert set(names) <= ticks.keys()
        controls = [ticks[n] for n in names]
        analysis = [v for k, v in ticks.items() if k not in names]
        assert min(analysis) - max(controls) > 1
        assert 'Microscope-control programs' in [t.get_text() for t in ax.texts]
        fig.canvas.draw()
    finally:
        plt.close(fig)
