# Validation data

This directory holds the sample inputs, frames, labels and audit records behind every validation figure and table in the paper. Three groups of files live here: the earlier root-level samples, the released replicate record under `replicates/`, and the frozen frames under `frames/`.

Nothing in this directory contains article text. Items carry identifiers (`epmc_id`, `pmcid`) and labels; the title and quoted-evidence columns were removed before publication. Labels describe sampling and agreement, so they support the reported precision and recall without redistributing source text.

## Replicate design

Each random-sample frame yields three disjoint seeded draws. When a frame holds fewer than three times the requested sample size, the pipeline treats it as a census, uses the whole frame and splits it into three balanced parts. Abstract package-years also split any frame of at most 2,000 records, matching the census rule of the main estimates. The union of the three parts covers the frame. Each draw writes an item CSV and a design record beside the labels.

## Annotation and agreement

Two independent annotators label each replicate item without seeing the query result. The aliases for each set are configured in `census.validation.label_replicates.ANNOTATORS`, and `ANNOTATORS.md` in this folder records the model behind each alias. Exact matching labels count as agreed; the scoring excludes disagreements from pooled agreed-label counts. Scoring reports agreement percentage and Cohen's kappa for each check and replicate.

Batch creation and response collection use a manual hand-off to an external agent runner. The first round uses:

```bash
python -m census.validation.label_replicates batches
python -m census.validation.label_replicates collect
python -m census.validation.label_replicates score
```

The second round repeats the original questions for the Cellpose workflow and research-area keywords:

```bash
python -m census.validation.label_round2 batches
python -m census.validation.label_round2 collect
python -m census.validation.label_round2 score
```

Electron microscopy is defined by use of the technique, so pooled area precision scores that area on a third round that asked whether the study uses or develops electron microscopy. Those labels carry the `_em` suffix, and `ROUND_FOR_AREA` in `census.validation.label_round2` records the choice.

## Data dictionary

### Root-level samples

The root CSVs preserve the earlier validation draws, with title and quoted-evidence columns removed.

| File | Row unit | Columns |
| --- | --- | --- |
| `alias_precision_2025.csv` | One sampled 2025 paper matched by a software name | `tool_id`, `pmcid`, `sense` (`software`, `other_sense`, `not_found`), `use` (`acquisition`, `analysis`, `unclear`, `na`) |
| `alias_precision_2025_items.csv` | One sampled item | `stratum`, `tool_id`, `year`, `epmc_id`, `pmcid` |
| `registry_precision_2026.csv` | One labelled match per package and sample | `tool_id`, `year`, `pmcid`, `label`, `use` (Photoshop context), `meaning` (NIH Image interpretation) |
| `photoshop_use_2025.csv` | One 2025 paper that used Photoshop on image data, re-labelled by two annotators | `pmcid`, `label_spark_glm`, `label_codex`, `label` (adjustment, measurement, unclear; authors resolved one disagreement) |
| `registry_precision_2026_items.csv`, `registry_precision_2026_nihimage_historical_items.csv` | One sampled paper | `stratum`, `tool_id`, `year`, `epmc_id`, `pmcid` |
| `cellpose_workflow_2025.csv` | One sampled paper | `pmcid`, `workflow` |
| `cellpose_workflow_2025_items.csv` | One sampled item | `stratum`, `tool_id`, `year`, `epmc_id`, `pmcid` |
| `dl_lexicon_2021_2025.csv` | One sampled abstract | `stratum`, `tool_id`, `year`, `epmc_id`, `label` |
| `dl_lexicon_2021_2025_items.csv` | One sampled item | `stratum`, `tool_id`, `year`, `epmc_id`, `pmcid` |
| `domain_keywords_2021_2025.csv` | One sampled keyword match | `area`, `epmc_id`, `tool_id`, `match`, `label` (`in_area`, `other_sense`) |
| `domain_keywords_2021_2025_items.csv` | One sampled item | `stratum`, `tool_id`, `year`, `epmc_id`, `pmcid` |
| `reporting_audit_labels_gemini.csv`, `reporting_audit_labels_syn.csv` | One audited paper, one annotator | `item_id`, `version`, `function`, `parameter`, `code` (each 0 or 1) |
| `citations_package_papers.csv` | One paper published by a package's own developers | `tool_id`, `epmc_id`, `source`, `year` (identifiers only; titles stay under the ignored `data/raw/citations/`) |
| `citations_named_not_cited_2021.csv`, `citations_named_not_cited_2025.csv` | One sampled paper that names a package but matches none of its reference terms | `tool_id`, `year`, `replicate`, `epmc_id`, `source`, `frame`, `n_refs`, `cited_work` (identifier or `None`) |
| `citations_cited_not_named_2025.csv` | One sampled paper that cites a package's papers without naming it | the same fields plus `full_text` and `name_in_full_text` (both Boolean indicators, no article text) |
| `wildcard_additions_2025.csv` | One sampled paper added by a trailing wildcard | `tool_id`, `replicate`, `epmc_id`, `source`, `frame`, `kind` (`exact`, `digits`, `letters`, `absent`), `token` |

`frame` gives the size of the frame a paper was drawn from, so a count of sampled rows can be read against its denominator. In the citation files, a `replicate` of 1, 2 or 3 marks the disjoint seeded draw.

### Released replicate record

`replicates/` is the versioned record that pooling reads.

| File pattern | Row unit | Columns |
| --- | --- | --- |
| `<set>_items_r<1-3>.csv` | One sampled item in one replicate | `stratum`, `tool_id`, `year`, `epmc_id`, `pmcid` |
| `<set>_labels_<annotator>_r<1-3>.csv` | One labelled item, one annotator | `item_id` plus the label fields for the set: `sense` and `use` (alias), `workflow` (Cellpose, StarDist, ilastik), `label` (deep-learning lexicon, research-area keywords), or `version`, `function`, `parameter`, `code` (reporting audit) |
| `<set>_design.json` | One set | `name`, `command`, `seed`, `replicate_sizes`, `anchor`, `note` |
| `<set>_RUBRIC.md` | One set | The labelling question, the allowed labels and the provenance |
| `cellpose_workflow_2025_human_r1.csv` | One hand-labelled paper | The human labels of replicate 1, read from the full text by one author (`cellpose_human_check_2025.csv` compares them with the model labels) |

The annotator names are `deepseek` and `glm`, or `syn` and `gemini` for the reporting audit. `item_id` joins the label and item files and is built from the item's own keys: `tool|epmc_id` for the alias and deep-learning sets, `area|tool|epmc_id` for research-area keywords, `tool|pmcid` for Cellpose, and `tool-pmcid` for the reporting audit.

A label file may carry a round suffix. A bare name is the first round, `_v2` is the second round, and `_em` is the third round used for Electron microscopy. Pooled outputs record which round entered each area.

### Frames

`frames/<set>_frame.csv` holds each frozen literature draw frame: alias precision, Cellpose workflow, the deep-learning lexicon, research-area keywords and registry precision. The registry-precision frames include the 2025 package draw, the NIH Image spelling-exclusion checks and a historical NIH Image draw covering 1995-2003. The corresponding JSON files record the queries, frame unit, registry digest and frame digest. The reporting audit draws its items from `data/processed/reporting_audit_papers_2025.csv`, so it has no frame file here.

## Pooled outputs

Run `python -m census.run_all --pool` after reviewing and committing the labels. It rebuilds the pooled files in `data/processed/` from committed labels and replicate records.

| File | Producer | Manuscript use |
| --- | --- | --- |
| `reporting_audit_pooled_2025.csv` | `census.validation.replicates:pool` | Table S1 and the reporting-audit Results |
| `reporting_audit_validation_pooled_2025.csv` | `census.validation.replicates:pool` | Pattern precision and recall in the reporting-audit Methods |
| `cellpose_workflow_pooled_2025.csv` | `census.validation.label_round2:pooled_cellpose` | Figure 6d and the validation table |
| `validation_pooled_2025.csv` | `census.validation.label_round2:pooled_validation` | Validation table and Methods |
| `domain_precision_2025.csv` | `census.validation.label_round2:area_precision` | Figure 5 area selection under the 50% rule, and the Figure 1 area labels |

The pooling functions count matching labels across the three replicates. Domain precision uses the agreed labels of the sampled keyword hits and applies the 50% cutoff when Figure 5 selects areas.

### Validation outputs in `data/processed/`

These files carry the validation results the manuscript quotes. Each builds from the labels above.

| File | Producer | Row unit and columns |
| --- | --- | --- |
| `reporting_audit_papers_2025.csv` | `census.build.build_reporting_audit` | One audited paper: the paper keys, `scope`, and the four indicator flags |
| `reporting_audit_2025.csv` | `census.validation.replicates:audit` | One package and replicate: sampled, analysed and fetched counts with the indicator totals |
| `reporting_audit_pooled_2025.csv` | `census.validation.replicates:pool` | One package: `n`, `analysed`, `fetched`, `in_methods_text`, then `<indicator>_n`, `<indicator>_pct`, `<indicator>_lo` and `<indicator>_hi` for version, function, parameter, code and complete |
| `reporting_audit_validation_pooled_2025.csv` | `census.validation.replicates:pool` | One indicator: `items`, `consensus_items`, the annotator-agreement range, the pattern true/false counts, and `precision_pct` and `recall_pct` |
| `reporting_audit_by_area_2025.csv` | `census.validation.audit_by_area` | One package: name-only counts with and without the computational-methods vocabulary, plus the vocabulary and missing-text counts |
| `reporting_audit_area_gap_2025.csv` | `census.validation.audit_by_area` | One row: the raw and stratified ImageJ/Fiji gap in percentage points with their sample sizes |
| `reporting_audit_area_missing_text_2025.csv` | `census.validation.audit_by_area` | One audited record with no available title or abstract |
| `validation_pooled_2025.csv` | `census.validation.label_round2:pooled_validation` | One metric: the three replicates and the pooled total |
| `cellpose_workflow_pooled_2025.csv`, `stardist_workflow_2025_pooled.csv`, `ilastik_workflow_2025_pooled.csv` | `census.validation.label_round2:pooled_cellpose` and `census.validation.workflow_hosts` | One workflow category: the three replicates, the pooled agreed count, and the total agreed and labelled items |
| `cellpose_human_check_2025.csv` | `census.validation.human_check` | One metric and value, comparing the human labels of replicate 1 with the model labels |
| `mesh_check_2021_2025.csv` | `census.validation.mesh_check` | One research area: `shown_in_figure`, the keyword, MeSH, both and major-heading counts, `n_available` (papers with a MeSH record), `annotator_precision`, and agreement, coverage and Cohen's kappa under any heading and major heading, each with Wilson and bootstrap intervals |
| `mesh_check_papers_2021_2025.csv` | `census.validation.mesh_check` | One sampled paper: `pmid`, `year`, `stratum`, `selection_probability` (the inverse-probability weight, one over the sampling fraction), `figure_row_count`, `figure_weight_sum`, `returned`, `has_mesh`, `is_in_medline`, a flag per research area, and `mesh_any__<area>` and `mesh_major__<area>` flags |

Rows in the MeSH files are distinct papers of the 2021-2025 research-area corpus, drawn as a stratified subsample of 3,000 sampled papers, 2,237 of which carry MeSH headings. Subset names stand in for MEDLINE indexing, since Europe PMC's core responses do not report an `isInMedline` field.

MeSH descriptor names in these files are content supplied by the U.S. National Library of Medicine, used courtesy of the U.S. National Library of Medicine. The per-area matching expressions are the authors' own mappings onto those names.

## Historical samples and ignored inputs

The root-level sample CSVs preserve the earlier validation draws. Reporting-audit pooling uses the paired root-level labels for replicate 1 and the replicate label CSVs for replicates 2 and 3.

The `data/raw/annotation/batches*` paths are ignored prompt batches, manifests, instructions and raw annotator responses. The committed item and label CSVs under `data/validation/replicates/` are the released record. Keep the ignored hand-off files out of the repository.
