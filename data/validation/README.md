# Validation data

This directory preserves the original sample CSVs, validation frames and the current replicate items and labels. The replicate record is under `data/validation/replicates/`.

## Replicate design

Each random-sample frame has three disjoint seeded draws. If a frame contains fewer than three times the requested sample size, the full frame is split at random into three balanced parts. Item CSVs and design records are committed beside the labels.

## Annotation and agreement

Two independent annotators label each replicate item blind to the query result. The aliases for each set are configured in `census.validation.label_replicates.ANNOTATORS`, and `ANNOTATORS.md` in this folder records the model behind each alias. Exact matching labels count as agreed; disagreements do not enter pooled agreed-label counts. Scoring reports agreement percentage and kappa per check and replicate.

Batch creation and response collection use a manual hand-off to an external agent runner. The first round uses:

```bash
python -m census.validation.label_replicates batches
python -m census.validation.label_replicates collect
python -m census.validation.label_replicates score
```

The second round repeats the original questions for Cellpose workflow and research-area keywords:

```bash
python -m census.validation.label_round2 batches
python -m census.validation.label_round2 collect
python -m census.validation.label_round2 score
```

Pooled area precision uses first-round labels for Electron microscopy, as specified by `USE_FIRST_ROUND` in `census.validation.label_round2`.

## Pooled outputs

Run `python -m census.run_all --pool` after reviewing and committing the labels. It rebuilds the five pooled files in `data/processed/` from committed labels and replicate records.

| File | Producer |
| --- | --- |
| `reporting_audit_pooled_2025.csv` | `census.validation.replicates:pool` |
| `reporting_audit_validation_pooled_2025.csv` | `census.validation.replicates:pool` |
| `cellpose_workflow_pooled_2025.csv` | `census.validation.label_round2:pooled_cellpose` |
| `validation_pooled_2025.csv` | `census.validation.label_round2:pooled_validation` |
| `domain_precision_2025.csv` | `census.validation.label_round2:area_precision` |

The validation functions pool matching labels across the three replicates. Domain precision uses the agreed labels for sampled keyword hits and applies a 50% cutoff when Figure 4 selects areas.

## Historical samples and ignored inputs

The root-level sample CSVs preserve the earlier validation draws. Reporting-audit pooling uses the paired root-level labels for replicate 1 and the replicate label CSVs for replicates 2 and 3.

The `data/raw/annotation/batches*` paths are gitignored prompt batches, manifests, instructions and raw annotator responses. The committed item and label CSVs under `data/validation/replicates/` are the released record. Keep the ignored hand-off files out of the repository.
