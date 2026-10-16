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
    text_columns = set(drake.select_dtypes(exclude="number").columns)
    assert text_columns <= {"tool_id", "download_record", "reason", "estimable"}
