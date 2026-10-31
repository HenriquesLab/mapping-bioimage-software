# Zenodo archive

The archive contains an exact copy of the committed repository tree plus five provenance files. It uses `git archive HEAD`, with no column stripping, generated sampling frames or added manuscript files during release. Development continues in this same public code and data repository.

## Build and check

Install the repository requirements and `pytest`. Commit all source and data changes first, then run from the repository root:

```bash
python release/make_release.py --version 2026.10.31.1
python -B release/test_release.py --archive release/build/mapping-bioimage-software-2026.10.31.1
```

The builder refuses staged, unstaged or untracked changes, a failing `tests/test_no_article_text.py`, and an existing output directory. Ignored local caches and the refetched corpus may remain. Use a new `--output` directory to preserve an earlier build. `release/build/` is ignored. Commands run offline and do not upload, publish, push or change branches.

The output directory contains exactly the tracked tree plus:

- `GIT_COMMIT.txt`: the archived commit
- `PROVENANCE.json`: version, commit and tracked file list
- `ENVIRONMENT.txt`: Python version and installed distributions directly imported by pipeline code, excluding standard-library and transitive-only imports
- `MANIFEST.tsv`: payload paths, byte counts and SHA-256 hashes, excluding the two manifest files
- `MANIFEST.sha256`: the manifest checksum

The checker verifies the full file set, checksums and every tracked byte against the recorded commit. Unit tests use isolated local Git repositories to exercise clean builds and refusals without needing a clean development checkout.

## Tracked sampling frames

`data/sampling_frames/` is a pipeline output committed before release. Rebuild it from the existing local caches with:

```bash
python -m census.build.build_sampling_frames
```

Tool-year frames contain Europe PMC `id,source` pairs in cached response order, including zero-result censuses. Reporting-audit frames contain sorted unique PMCIDs. Validation frames contain identifiers, strata and portable provenance sidecars. The builder makes no network requests. Its `metadata.json` records queries, source-cache checksums, population drift and completeness. The eight known incomplete cached frames and their issues appear in `data/sampling_frames/README.md`. These limit exact reproduction and are never repaired silently.

## Article text and local refetching

The tracked tree contains no source-article titles, abstracts, full text or quoted annotation evidence. `tests/test_no_article_text.py` enforces that at the source. The release builder copies tracked bytes unchanged. Code uses MIT (`LICENSE`) and derived data use CC BY 4.0 (`LICENSE-DATA`); these grant no rights to underlying article text.

Refetch the sampled corpus by its frozen identifiers, subject to each source record's licence:

```bash
python release/refetch_identifiers.py --archive . --output data/processed/random_sample_2021_2025.csv.gz --allow-network
python -m pytest -q -rs
```

The helper preserves selected identifiers, populations, sample sizes, journal metadata and row order, resolves sources from the frozen tool-year frames and refuses an existing output. Keep the refetched corpus local and ignored. The Supplementary Figure 2 build and enrichment byte-comparison tests skip without it. The two SI comparison tests need the manuscript checkout. The pooled audit comparison needs private raw replicate records; query-error checks need the private citation-validation `full_text` indicator. Each reports a skip reason when its input is absent. Cache-rebuild comparison tests also skip when local API caches are absent; tracked frames remain usable.

Processed results and figure notebooks ship in the tracked tree. Existing pipeline builders can query current records and overwrite outputs, so run new analyses in a separate reproduction copy. Frozen tool-year sampling uses `random.Random(f"20260929-{tool_id}-{year}")`, taking the whole frame up to `max(2000, cap)` and otherwise drawing at the configured cap. Frame order matters.

A validation redraw can use a frozen frame and the seed recorded in its item metadata:

```bash
python -m census.validation.draw_validation_samples cellpose --frame data/sampling_frames/validation/cellpose_workflow_2025_frame.csv --seed 20261006-validation-redraw-v1 --output-dir release/redraw
```

Use the corresponding alias, lexicon or domain frame for those draws. Historical labels have unrecovered drawing provenance; a fresh seed does not establish the original selection. Sidecar input hashes describe original inputs; the archive manifest hashes the committed copies.

## Citation

Use `CITATION.cff` and `.zenodo.json`. Version 2026.10.31.1 uses the reserved DOI https://doi.org/10.5281/zenodo.23834350. Building this local archive does not publish the record.
