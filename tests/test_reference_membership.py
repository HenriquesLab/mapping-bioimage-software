"""Reference environments retain their queries but enter no denominator."""

from census._registry import load_registry
from census.build import build_dataset
from census.figures import style as fs


def test_jupyter_reference_membership(tmp_path, monkeypatch):
    reg = load_registry()
    jupyter = reg.by_id("jupyter")
    assert jupyter.aliases == ["Jupyter", "Jupyter notebook", "IPython notebook"]
    assert jupyter.category == "notebook"
    assert jupyter.scope == "core"
    monkeypatch.setattr(build_dataset, "PROCESSED_DIR", tmp_path)
    tools = build_dataset.write_tools(reg)
    monkeypatch.setattr(fs, "load", lambda name: tools)
    photoshop = reg.by_id("photoshop")
    assert photoshop.category == "figure-preparation"
    assert not photoshop.in_aggregate
    for members in (fs.analysis_tools(), fs.aggregate_tools(), fs.core_tools()):
        assert "jupyter" not in members
        assert "matlab" not in members
        assert "photoshop" not in members
    assert "imagepro" in set(fs.analysis_tools())
    assert "nihimage" not in set(fs.analysis_tools())
    assert len(fs.analysis_tools()) == 23
    assert len(fs.aggregate_tools()) == 29
    assert len(fs.core_tools()) == 13
