<p align="center"><img src="logo/mapping-bioimage-software-logo.svg" alt="mapping-bioimage-software logo" width="220"></p>

# mapping-bioimage-software

## Purpose and scope

This repository is the public home of the code and data for the paper *Mapping bioimage-analysis software adoption in microscopy*. The package measures how often selected image-analysis software appears in microscopy literature and supports the manuscript's annual counts, deep-learning estimates, research-area analysis, reporting audit and adoption snapshots.

Run pipeline modules from the repository root with `python -m census.<module>`. The `census/` package works in this repository and in the manuscript repository's `scripts/` checkout.

The registry contains 30 packages: 22 analysis packages, six microscope-control programs, and MATLAB and Jupyter notebooks as references outside all aggregates. The deep-learning series uses 13 core analysis packages. Jupyter notebooks retain their aliases, notebook category and core scope. Frozen validation designs and labels retain the original 14-package calibration sample.

## What is measured and study limits

The builders combine annual Europe PMC and OpenAlex counts for package names with a microscopy-paper denominator. A configured lexicon classifies deep-learning terms in sampled titles and abstracts. The pipeline applies each sample's measured fraction to the relevant yearly count. It also compares research-area keywords across sampled 2021–2025 abstracts, counts host-platform co-mentions for Cellpose and StarDist, audits software reporting in Methods sections, and records GitHub stars and forks, 30-day PyPI downloads and image.sc topics.

Mention counts measure reporting frequency. They cannot establish whether authors ran the named software. Papers that name two packages do not establish their integration. The registry and lexicons define a selected scope.

Deep-learning estimates depend on abstract coverage and configured terms. Each tool-year reads up to its `dl_sample_cap` records (200 by default; 1,000 for ImageJ/Fiji and Imaris in `config/tools.yml`), and frames of at most 2,000 records are read in full. Adoption indicators record public service counts at collection time. Validation summaries describe sampled items and include only agreed labels.

## Layout

```text
census/
  _http.py                 shared request and cache helpers
  _paths.py                canonical repository paths
  _registry.py             tool registry and query construction
  run_all.py               pipeline orchestrator
  build/                   dataset builders, classifiers and sensitivity checks
    classify_dl.py         deep-learning lexicon classifier
    build_citations_by_source.py  citation coverage by mention source
    build_reach_any.py     yearly reach, counting each paper once
  figures/                 main and supplementary figure builders
  sources/                 Europe PMC, OpenAlex, GitHub, PyPI and image.sc clients
  tables/
    make_si_tables.py      Supplementary Information table updater
  validation/              draws, replicates, annotation and audit checks
    replicates.py
    label_replicates.py
    label_round2.py
    workflow_hosts.py      StarDist and ilastik workflow checks
    human_check.py         human check of Cellpose workflow labels
config/                    tool registry, lexicons and analysis settings
data/
  raw/                     ignored API caches and annotation hand-off files
  sampling_frames/         frozen identifier lists and completeness metadata
  processed/               committed analysis CSVs and pooled outputs
    replicates/            replicate results and deviation summaries
  validation/              validation items, frames and committed labels
notebooks/                 figure walkthroughs
release/                   archive builder, checks and release notes
tests/                     package and output tests
```

## Installation

Use Python 3.11 or later. From the repository root, create an environment and install the pipeline requirements:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For the figure walkthrough notebooks, install the optional requirements:

```bash
python -m pip install -r requirements-notebooks.txt
```

## Standard run and outputs

Run the full pipeline from the repository root:

```bash
python -m census.run_all
```

The run rebuilds processed CSVs and the Supplementary Information tables (written to `tables/output/supplementary_tables.md`; in the manuscript checkout, into its SI file), plus figures in the manuscript checkout. API responses are cached under `data/raw/`. Missing cache entries can require live source requests. Use `--no-figures` to build data without figures or tables, or `--lit-only` for the literature tables.

Europe PMC counts shift slightly over time, so a rebuild from live sources can differ in the last digits from the committed `data/processed/` files (for example, a count off by one). These small changes are expected and do not affect the conclusions.

```bash
python -m census.run_all --no-figures
python -m census.run_all --lit-only
python -m census.build.classify_dl --tool cellpose --year 2025
```

`--sample-cap` sets the fallback sample cap; per-tool caps in `config/tools.yml` take precedence. `--validation-seed` sets the recorded seed for fresh validation draws. `--audit` builds the reporting audit and draws its validation items. `--draw-validation` creates fresh identifier lists for selected validation sets. Both keep label collection as a separate step.

## Replicate design

Each random-sample frame produces three disjoint seeded draws. When a frame contains fewer than three times the requested sample size, the pipeline uses the whole frame and splits it at random into three balanced parts. Abstract tool-years also split any frame of at most 2,000 records, matching the census rule of the main estimates, so some census-split frames exceed three times the cap. The union of the parts covers the frame.

Run the automated preparation and summary stages with:

```bash
python -m census.run_all --replicates
```

This runs these commands in order: `python -m census.validation.replicates draw`, `python -m census.validation.replicates abstracts`, `python -m census.validation.replicates audit`, `python -m census.validation.replicates validation` and `python -m census.validation.replicates summarise`. The sequence prepares items and summaries. Annotation is a separate manual hand-off described below.

## Annotation

Two independent annotators label each validation item blind to the query result. The annotator aliases for each set are defined in `census.validation.label_replicates.ANNOTATORS`; `data/validation/ANNOTATORS.md` maps each alias to the model identifier used and the commit that holds its labels. Exact matches form the agreed labels; disagreements are excluded from pooled agreed-label counts. The scoring commands report agreement percentage and kappa for each check and replicate.

Batch generation and response collection for both rounds use a manual hand-off to an external agent runner. For the first round, run these commands from `scripts/`:

```bash
python -m census.validation.label_replicates batches
python -m census.validation.label_replicates collect
python -m census.validation.label_replicates score
```

The batch command writes prompts and a manifest under `data/raw/annotation/batches/`. An external runner processes the prompts for both annotators. Collection validates the responses and writes label CSVs under `data/validation/replicates/`.

The second round repeats the original questions for the Cellpose workflow and research-area keywords. Cellpose batches include Methods text; area batches include the matched keyword and its sentence. Run:

```bash
python -m census.validation.label_round2 batches
python -m census.validation.label_round2 collect
python -m census.validation.label_round2 score
```

Pooled area precision uses first-round labels for Electron microscopy, as defined by `USE_FIRST_ROUND` in `census.validation.label_round2`.

## Pooled outputs

After reviewing and committing the label CSVs, run `python -m census.run_all --pool`. It calls `python -m census.validation.replicates pool` and then `python -m census.validation.label_round2 pooled`. The command rebuilds all five pooled CSVs from committed labels and replicate records. It does not run the external annotation hand-off.

| File | Producing function | Manuscript use |
| --- | --- | --- |
| `data/processed/reporting_audit_pooled_2025.csv` | `census.validation.replicates:pool` | Table S1 and reporting-audit Results |
| `data/processed/reporting_audit_validation_pooled_2025.csv` | `census.validation.replicates:pool` | Pattern precision and recall in the reporting-audit Methods (checked by `tools/check_numbers.py`) |
| `data/processed/cellpose_workflow_pooled_2025.csv` | `census.validation.label_round2:pooled_cellpose` | Figure 5d, Results and the validation table |
| `data/processed/validation_pooled_2025.csv` | `census.validation.label_round2:pooled_validation` | Validation table and Methods |
| `data/processed/domain_precision_2025.csv` | `census.validation.label_round2:area_precision` | Figure 4 area selection using the 50% rule and its caption; Figure 1 area labels |
| `data/processed/replicates/deviation_summary.csv` | `census.validation.replicates:summarise` | Spread between replicates; internal check, quoted nowhere in the manuscript |

## Key processed datasets

| Dataset | Contents | Key columns |
| --- | --- | --- |
| `data/processed/adoption_snapshot.csv` | Cross-sectional adoption metrics across packages | `tool_id`, `category`, `github_stars`, `github_forks`, `pypi_downloads_30d` |
| `data/processed/dl_estimates.csv` | Annual deep-learning share and sample counts by package | `tool_id`, `year`, `population`, `n_sampled`, `n_dl`, `dl_fraction` |
| `data/processed/domain_enrichment.csv` | Research-area keyword frequencies in package abstracts | `tool_id`, `domain`, `share`, `baseline`, `ratio` |
| `data/processed/mentions_citations_yearly.csv` | Annual mentions, citations and uncited counts | `tool_id`, `year`, `named`, `cited`, `both`, `named_not_cited` |
| `data/processed/drake_2021_2025.csv` | Pooled downloads, citations and ratios for 2021–2025, plus ImageJ/Fiji's 2020 report | `tool_id`, `downloads`, `citations`, `c_measured`, `estimable` |
| `data/processed/drake_yearly.csv` | Annual downloads, citations and downloads per citing paper for QuPath, Cellpose and StarDist | `tool_id`, `year`, `downloads`, `citations`, `downloads_per_citing_paper` |
| `data/processed/methods_section_2025.csv` | Reporting audit counts in 2025 Methods sections | `tool_id`, `n_all`, `n_methods`, `share_methods` |
| `data/processed/reach_any_yearly.csv` | Combined annual reach across tracked packages | `year`, `group`, `papers` |

## Validation data and ignored inputs

The committed item and label CSVs under `data/validation/replicates/` are the released replicate record. Root-level validation CSVs preserve the earlier samples and reporting-audit labels, with their title and quoted-evidence columns removed. The `data/raw/annotation/batches*` paths are gitignored prompt batches, manifests, instructions and raw responses. Keep the collected CSV labels under `data/validation/replicates/` as the versioned analysis record.

## Notebooks

`notebooks/` contains walkthroughs for Figures 1–6 and Supplementary Figures 1–3. Install `requirements-notebooks.txt` after the base requirements to execute them.

## Release archive

`release/make_release.py` builds the Zenodo archive from the exact committed tree plus five provenance files. It refuses a dirty working tree or a failing article-text guard and performs no column stripping. Sampling frames are tracked pipeline outputs under `data/sampling_frames/`; their README documents eight incomplete cached frames.

Commit changes, then build and check offline:

```bash
python release/make_release.py --version 2026.10.23
python -B release/test_release.py --archive release/build/mapping-bioimage-software-2026.10.23
```

The builder refuses an existing output directory; use `--output` for another copy. The checker verifies the exact file set and hashes. See `release/README.md` for provenance and frame-rebuild commands.

## Testing

Install `requirements.txt` and `pytest`, then run:

```bash
python -m pytest -q -rs
```

A fresh clone skips the Supplementary Figure 2 build and enrichment byte comparison
without `data/processed/random_sample_2021_2025.csv.gz`. Rebuild that local corpus
from the archived identifiers (requires network access), then rerun the tests:

```bash
python release/refetch_identifiers.py --archive . --output data/processed/random_sample_2021_2025.csv.gz --allow-network
python -m pytest -q -rs
```

The pooled audit comparison requires the private `data/raw/replicates/audit/*.json` records. The query-error row-count and wording tests require the `full_text` indicator in the private citation-validation CSV; the public data omit that column. These tests skip with reasons when their
inputs are absent. The wildcard-table and notebook-renderer checks still run
in a fresh clone; notebook inspection needs no Jupyter installation. The frame-rebuild
comparison also skips without local API caches; committed frames need no refetch.

## Article text

The repository and archive contain identifiers and derived data, with no source-article titles, abstracts or full text. Redistribution rights vary by record. `data/processed/random_sample_2021_2025_ids.csv` records the sampled abstracts by identifier; the text file the deep-learning, research-area and term analyses read (`random_sample_2021_2025.csv.gz`) is gitignored. Rebuild it locally from Europe PMC with `release/refetch_identifiers.py` (see `release/README.md`); the committed results (`dl_estimates.csv`, `domain_enrichment.csv` and the figures) need no refetch. See `release/README.md` for the archive contents, reproduction steps and environment record.

## Data sources and terms

Each source is queried through its public API, and the counts are recorded at collection time.

**Europe PMC.** The search API supplies annual mention counts and the open-access full text supplies the sampled abstracts and Methods sections. Records derived from MEDLINE/PubMed carry the NLM notice that the data may not be current and that NLM does not endorse this work. Full text was mined for the analysis and never redistributed. Courtesy of the U.S. National Library of Medicine.

**OpenAlex.** Annual counts for the same package names, available under CC0.

**GitHub REST API.** Public repository counts, stars and forks, collected on 1 September 2026. GitHub's Acceptable Use Policies allow research use of public, non-personal information when the resulting publications are open access; the paper is released open access on bioRxiv.

**pypistats.org.** Thirty-day PyPI download totals, collected on 1 September 2026. pypistats.org derives them from the Python Software Foundation's PyPI download dataset on Google BigQuery (`bigquery-public-data.pypi`), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The archive keeps only one 30-day total per package.

**Users-and-downloads analysis.** We collected annual PyPI downloads on 16 October 2026 from the public ClickHouse mirror of the Python Software Foundation's PyPI BigQuery dataset (CC BY 4.0: https://creativecommons.org/licenses/by/4.0/). GitHub totals sum release-asset downloads by release year. OpenAlex provides yearly citations under CC0. The image.sc discussion reports 500,000 Fiji downloads in 2020 (https://forum.image.sc/t/51313).

**MeSH.** The MeSH check (`census/validation/mesh_check.py`) compares research-area keywords with Medical Subject Headings from MEDLINE records retrieved through Europe PMC on 15 October 2026, indexed with the 2026 MeSH vocabulary. `config/mesh_areas.yml` names MeSH descriptors, which are NLM content used under NLM's terms; the processed files keep identifiers and match flags only. Courtesy of the U.S. National Library of Medicine.

**image.sc forum.** Topic counts only; the pipeline collects no posts.

**Crossref and ORCID.** Bibliographic metadata for the packages' own papers and author identifiers, available under CC0.

The repository contains no source-article titles, abstracts or full text; article records use identifiers only. `release/refetch_identifiers.py` rebuilds the text corpus from the released identifiers through Europe PMC.

## Citing

Cite the archived release with the metadata in `CITATION.cff`. Zenodo DOI: https://doi.org/10.5281/zenodo.23528077.

## Licence

The code (`census/`, `release/`, `tests/`, and the code cells of `notebooks/`) and configuration (`config/`) are licensed under MIT (`LICENSE`). The data in `data/` and the figures and text the notebooks produce are licensed under CC BY 4.0 (`LICENSE-DATA`). CC BY 4.0 covers the authors' own selection, labels and derived data; the factual and public-domain inputs it draws on (counts, identifiers, MEDLINE metadata) remain under their sources' terms above. `THIRD_PARTY_NOTICES.md` gives the licence of the copied scikit-learn stop-word list.

## Contributing and issues

Open an issue on GitHub (`https://github.com/HenriquesLab/mapping-bioimage-software/issues`) to report discrepancies, suggest package additions or ask questions about data reproduction.

## AI assistance disclosure

Language models supported code drafting, query formulation and blinded validation scoring. All code, analyses and findings were designed and verified by the authors.
