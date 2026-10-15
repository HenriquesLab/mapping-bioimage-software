from census.figures import fig3_citations as f3


def test_partition_preserves_the_observed_union():
    tab = f3.table()
    u = f3.union(tab)
    observed = tab.named + tab.cited - tab.both
    assert ((u.no + u.both + u.co - observed).abs() < 1e-6).all()
    assert (u[['no', 'both', 'co']] >= 0).all().all()
    assert ((u.no_pct + u.both_pct + u.co_pct - 100).abs() < 1e-6).all()


def test_figure_uses_citation_links_only():
    assert set(f3.table().index) == {'imagej', 'qupath', 'cellprofiler', 'ilastik', 'icy', 'cellpose',
                                      'deepimagej', 'zerocostdl4mic', 'skimage'}
