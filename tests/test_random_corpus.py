from types import SimpleNamespace
import sys

import pandas as pd
import yaml

from census.build import random_corpus


def test_selected_tools_replace_rows_and_write_matching_identifier_file(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    config = tmp_path / "tools.yml"
    config.write_text(yaml.safe_dump({"tools": [{"id": "imagej"}, {"id": "imagepro"}]}))
    monkeypatch.setattr(random_corpus, "PROCESSED_DIR", processed)
    monkeypatch.setattr(random_corpus, "TOOLS_YML", config)
    monkeypatch.setattr(random_corpus, "ensure_dirs", lambda: None)
    monkeypatch.setattr(
        random_corpus,
        "load_registry",
        lambda: SimpleNamespace(tools=[SimpleNamespace(id="imagej"), SimpleNamespace(id="imagepro")]),
    )

    def sample(tool, registry, year, cap):
        return ([{
            "tool_id": tool.id,
            "year": year,
            "epmc_id": f"new-{year}",
            "venue": "Synthetic Journal",
            "title": "Synthetic title",
            "abstract": "Synthetic abstract",
        }], 3)

    monkeypatch.setattr(random_corpus.europepmc, "random_sample_works", sample)
    existing = pd.DataFrame([
        {"tool_id": "imagej", "year": 2021, "epmc_id": "old-1", "population": 5,
         "n_sampled": 1, "venue": "Old Journal", "title": "Old title", "abstract": "Old abstract"},
        {"tool_id": "imagepro", "year": 2021, "epmc_id": "stale-1", "population": 9,
         "n_sampled": 1, "venue": "Old Journal", "title": "Stale title", "abstract": "Stale abstract"},
    ])
    existing.to_csv(processed / "random_sample_2021_2025.csv.gz", index=False)
    monkeypatch.setattr(sys, "argv", ["random_corpus", "--tool", "imagepro"])

    random_corpus.main()

    corpus = pd.read_csv(processed / "random_sample_2021_2025.csv.gz", dtype={"epmc_id": str})
    ids = pd.read_csv(processed / "random_sample_2021_2025_ids.csv", dtype={"epmc_id": str})
    assert set(corpus["epmc_id"]) == {"old-1", *(f"new-{year}" for year in range(2021, 2026))}
    assert list(ids.columns) == ["tool_id", "year", "epmc_id", "population", "n_sampled", "venue"]
    assert ids[["tool_id", "year", "epmc_id"]].equals(corpus[["tool_id", "year", "epmc_id"]])
    assert "abstract" not in ids.columns and "title" not in ids.columns
