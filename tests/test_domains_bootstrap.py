"""Contracts for the paper-clustered research-area bootstrap."""
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from census.figures import domains


def _frame(outcomes, *, census=False, shared_ids=False):
    rows = []
    for tool, values in outcomes.items():
        n = len(values)
        population = n if census else 2 * n
        for i, present in enumerate(values):
            row = {
                "tool_id": tool,
                "year": 2021,
                "epmc_id": f"paper-{i}" if shared_ids else f"{tool}-{i}",
                "population": population,
                "n_sampled": n,
                "w": population / n,
            }
            row.update({area: present for area in domains.DOMAINS})
            rows.append(row)
    return pd.DataFrame(rows)


def test_point_estimates_use_design_weights_without_bootstrap_multipliers(monkeypatch):
    monkeypatch.setattr(domains, "MIN_PAPERS", 1)
    data = _frame(
        {"package-a": [True] * 8 + [False] * 8,
         "package-b": [True] * 4 + [False] * 12},
        shared_ids=True,
    )

    result = domains.enrichment(data, n_boot=20, seed=7)
    result = result[result["domain"] == "Neuroscience"].set_index("tool_id")

    assert result.loc["package-a", "share"] == pytest.approx(50.0)
    assert result.loc["package-a", "baseline"] == pytest.approx(25.0)
    assert result.loc["package-a", "ratio"] == pytest.approx(2.0)
    assert result.loc["package-b", "share"] == pytest.approx(25.0)
    assert result.loc["package-b", "baseline"] == pytest.approx(50.0)
    assert result.loc["package-b", "ratio"] == pytest.approx(0.5)


def test_census_strata_have_no_bootstrap_interval(monkeypatch):
    monkeypatch.setattr(domains, "MIN_PAPERS", 1)
    data = _frame(
        {"package-a": [True, True, False, False],
         "package-b": [True, False, False, False]},
        census=True,
        shared_ids=True,
    )

    result = domains.enrichment(data, n_boot=100, seed=11)

    assert (result["lo"].to_numpy() == result["ratio"].to_numpy()).all()
    assert (result["hi"].to_numpy() == result["ratio"].to_numpy()).all()
