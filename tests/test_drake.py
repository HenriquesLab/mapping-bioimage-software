"""Offline checks for the users-and-downloads analysis."""
import numpy as np
import pandas as pd
import pytest

from census._paths import PROCESSED_DIR
from census.figures import fig3_citations


@pytest.fixture
def drake():
    return pd.read_csv(PROCESSED_DIR / "drake_2021_2025.csv")


def test_estimable_ratios_use_downloads_and_citations(drake):
    rows = drake[drake.estimable]
    assert set(rows.tool_id) == {"qupath", "cellpose", "stardist", "imagej"}
    assert np.allclose(rows.downloads_per_citing_paper, rows.downloads / rows.citations)
    assert np.allclose(rows.downloads_per_mention_or_citation,
                       rows.downloads / (rows.citations * rows.c_measured))
    unavailable = drake[~drake.estimable]
    assert unavailable.downloads_per_citing_paper.isna().all()
    assert unavailable.downloads_per_mention_or_citation.isna().all()


def test_c_measured_matches_citation_link_union(drake):
    citation_union = fig3_citations.union(fig3_citations.table())
    expected = 100 / (100 - citation_union.no_pct)
    actual = drake.set_index("tool_id").c_measured
    shared = expected.index.intersection(actual.index)
    assert len(shared) > 0
    assert np.allclose(actual.loc[shared], expected.loc[shared])


def test_csv_has_no_unexpected_text_columns(drake):
    text_columns = set(drake.select_dtypes(include="object").columns)
    assert text_columns == {"tool_id", "download_record", "reason"}


def test_si_table_formats_estimable_and_unestimable_rows():
    from census.tables import make_si_tables

    table = make_si_tables.TABLES["drake"]()
    rows = table.splitlines()
    assert rows[:6] == [
        "| Package | Download record | Downloads | Citations | C | Downloads per citing paper | Per paper mentioning or citing |",
        "|---|---|---|---|---|---|---|",
        "| QuPath | GitHub installers | 868,872 | 6,647 | 1.91 | 130.7 | 68.3 |",
        "| Cellpose | PyPI | 1,356,570 | 4,497 | 1.21 | 301.7 | 249.8 |",
        "| StarDist | PyPI | 507,840 | 1,603 | 1.35 | 316.8 | 235.5 |",
        "| ImageJ/Fiji | reported (image.sc, 2020) | 500,000 | 12,951 | 7.30 | 38.6 | 5.3 |",
    ]
    assert rows[6:] == [
        "| CellProfiler | installers mostly downloaded from cellprofiler.org, which publishes no counts | – | – | – | – | – |",
        "| ilastik | installers downloaded from ilastik.org, which publishes no counts | – | – | – | – | – |",
        "| napari | cited mainly through a software record | – | – | – | – | – |",
        "| scikit-image | installed mostly as a dependency of other packages | – | – | – | – | – |",
        "| OpenCV | installed mostly as a dependency of other packages | – | – | – | – | – |",
        "| Jupyter notebooks | installed mostly as a dependency of other packages | – | – | – | – | – |",
    ]
