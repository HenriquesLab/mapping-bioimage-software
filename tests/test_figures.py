"""Headless figure contracts, with no data writes during rendering."""
import importlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODULES = [
    "fig1_overview", "fig2_landscape", "fig3_citations", "fig4_reach", "fig5_domains",
    "fig6_deep_learning", "sfig1_trajectories", "sfig2_terms", "sfig3_triangulation",
]


@pytest.mark.parametrize("name", MODULES)
def test_build_figure(name):
    module = importlib.import_module(f"census.figures.{name}")
    from census._paths import PROCESSED_DIR
    if name == 'sfig2_terms' and not (PROCESSED_DIR / 'random_sample_2021_2025.csv.gz').is_file():
        pytest.skip('Text corpus is not shipped; rebuild with release/refetch_identifiers.py')
    csv = PROCESSED_DIR / "domain_enrichment.csv"
    before = (csv.read_bytes(), csv.stat().st_mtime_ns)
    fig = module.build_figure()
    try:
        assert isinstance(fig, Figure)
        fig.canvas.draw()
        assert (csv.read_bytes(), csv.stat().st_mtime_ns) == before
    finally:
        plt.close(fig)


def test_enrichment_bytes():
    from census.figures import domains
    from census._paths import PROCESSED_DIR
    if not (PROCESSED_DIR / 'random_sample_2021_2025.csv.gz').is_file():
        pytest.skip('Text corpus is not shipped; rebuild with release/refetch_identifiers.py')
    reference = (PROCESSED_DIR / "domain_enrichment.csv").read_bytes()
    rebuilt = domains.enrichment(domains.load_corpus()).to_csv(index=False).encode()
    assert rebuilt == reference


def test_default_output_directory():
    from census.figures import style
    from census._paths import FIGURES_DIR, SCRIPTS_DIR
    expected = FIGURES_DIR if FIGURES_DIR.is_dir() else style.SCRIPTS_DIR / "figures" / "output"
    assert style.default_output_dir() == expected


def test_standalone_output_and_explicit_save(tmp_path, monkeypatch):
    from census.figures import style
    monkeypatch.setattr(style, "FIGURES_DIR", tmp_path / "missing-manuscript")
    assert style.default_output_dir() == style.SCRIPTS_DIR / "figures" / "output"
    fig = plt.figure()
    try:
        destination = tmp_path / "new-output"
        style.save(fig, "probe", out_dir=destination)
        assert {p.suffix for p in destination.iterdir()} == {".png", ".pdf", ".svg"}
    finally:
        plt.close(fig)


def test_notebooks_use_the_single_publication_renderer():
    notebooks = sorted((Path(__file__).resolve().parents[1] / "notebooks").glob("*.ipynb"))
    assert len(notebooks) == len(MODULES)
    for path in notebooks:
        notebook = json.loads(path.read_text(encoding='utf-8'))
        assert notebook['metadata']['kernelspec']['name'] == "bioimage-figures"
        assert "legacy" not in ''.join(notebook['cells'][0]['source']).lower()
