"""Release figures keep their layout without leaking warning source paths."""
import warnings

import matplotlib.pyplot as plt
import pytest

from census.figures import fig2_landscape, sfig3_triangulation


@pytest.mark.parametrize('module', [fig2_landscape, sfig3_triangulation])
def test_layout_warning_is_silenced_without_changing_axes(module):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        fig = module.build_figure()
    try:
        assert len(fig.axes) == (3 if module is fig2_landscape else 4)
        assert not any('not compatible with tight_layout' in str(w.message) for w in caught)
    finally:
        plt.close(fig)
