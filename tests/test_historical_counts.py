from types import SimpleNamespace

from census._registry import Registry, Tool
from census.sources import europepmc


def test_europepmc_yearly_counts_accepts_explicit_years(monkeypatch):
    tool = Tool(
        id="metamorph",
        name="MetaMorph",
        category="commercial",
        implies_dl=False,
        aliases=["MetaMorph"],
    )
    registry = Registry(
        year_start=2010,
        year_end=2010,
        context_query="(microscopy OR microscope) AND HAS_FT:Y",
        tools=[tool],
    )
    seen = []

    def fake_count(query):
        seen.append(query)
        return int(query.rsplit("PUB_YEAR:", 1)[1])

    monkeypatch.setattr(europepmc, "_hit_count", fake_count)
    counts = europepmc.yearly_counts(tool, registry, years=[1997, 1995])

    assert counts == {1995: 1995, 1997: 1997}
    assert len(seen) == 2
    assert any("PUB_YEAR:1995" in query for query in seen)
    assert any("PUB_YEAR:1997" in query for query in seen)
    assert all("PUB_YEAR:2010" not in query for query in seen)


def test_europepmc_yearly_counts_defaults_to_registry_window(monkeypatch):
    tool = Tool("metamorph", "MetaMorph", "commercial", False, ["MetaMorph"])
    registry = Registry(2010, 2011, "(microscopy OR microscope) AND HAS_FT:Y", [tool])
    monkeypatch.setattr(
        europepmc,
        "_hit_count",
        lambda query: int(query.rsplit("PUB_YEAR:", 1)[1]),
    )

    assert europepmc.yearly_counts(tool, registry) == {2010: 2010, 2011: 2011}


def test_historical_builder_writes_package_and_corpus_years(monkeypatch, tmp_path):
    from census.build import build_history

    tool = Tool("metamorph", "MetaMorph", "commercial", False, ["MetaMorph"])
    registry = SimpleNamespace(
        year_start=2010,
        context_query="(microscopy OR microscope) AND HAS_FT:Y",
        tools=[tool],
    )
    expected_years = list(range(1995, 2010))
    calls = []

    def package_counts(tool, reg, years):
        calls.append(("package", list(years)))
        return {year: 2 for year in years}

    def corpus_counts(query, years):
        calls.append(("corpus", list(years)))
        assert query == registry.context_query
        return {year: 100 for year in years}

    monkeypatch.setattr(build_history.europepmc, "yearly_counts", package_counts)
    monkeypatch.setattr(build_history.europepmc, "yearly_query_counts", corpus_counts)
    mentions, corpus = build_history.build_historical_counts(registry, output_dir=tmp_path)

    assert calls == [("package", expected_years), ("corpus", expected_years)]
    assert mentions["year"].tolist() == expected_years
    assert mentions["count"].tolist() == [2] * 15
    assert corpus["year"].tolist() == expected_years
    assert corpus["microscopy_papers"].tolist() == [100] * 15
    assert (tmp_path / "historical_mentions_yearly.csv").is_file()
    assert (tmp_path / "historical_corpus_yearly.csv").is_file()


def test_history_figure_covers_1995_to_2025_with_corpus_panel():
    import pandas as pd
    import matplotlib.pyplot as plt
    from census.figures import sfig4_history

    years = list(range(1995, 2026))
    counts = pd.DataFrame([
        {"tool_id": tool, "year": year, "count": i + 1}
        for tool, i in (("metamorph", 3), ("photoshop", 1))
        for year in years
    ])
    corpus = pd.Series({year: 5_000 + 100 * (year - 1995) for year in years})
    tools = pd.DataFrame([
        {"tool_id": "metamorph", "name": "MetaMorph", "category": "commercial", "in_aggregate": True},
        {"tool_id": "photoshop", "name": "Photoshop", "category": "figure-preparation", "in_aggregate": False},
    ]).set_index("tool_id")

    fig = sfig4_history.build_figure(counts=counts, corpus=corpus, tools=tools)
    try:
        assert len(fig.axes) == 3
        assert tuple(fig.axes[0].get_xlim()) == (1995, 2025)
        assert fig.axes[0].get_yscale() == "log"
        metamorph_ax = next(ax for ax in fig.axes[1:] if "MetaMorph" in ax.get_title(loc="left"))
        assert tuple(metamorph_ax.lines[0].get_xdata()) == tuple(years)
        assert metamorph_ax.lines[0].get_color() == sfig4_history.fs.CATEGORY_COLOR["commercial"]
        assert metamorph_ax.patches
    finally:
        plt.close(fig)
