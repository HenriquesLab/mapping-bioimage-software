# Rubric: Alias precision sample, core packages

## Labelling question

Does the matched name refer to the named software package, and was it used for image acquisition or analysis?

## Allowed labels

`not_found`, `other_sense`, `software`, ``, `acquisition`, `analysis`, `unclear`

## Inputs

The annotation bundle gives the identifier, the package and the text.
For abstract-based sets that is the title and abstract; for full-text sets it is the
Methods mention windows and a full-text excerpt around the named package. No pattern or
classifier result is shown.

## Provenance

Reconstructed from the existing label files, `data/validation/README.md`
and the manuscript Methods sections (Validation samples; Host-platform co-mentions and
the Cellpose sample; Reporting audit). Two independent annotators label each replicate.

