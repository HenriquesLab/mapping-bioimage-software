# Rubric: Cellpose workflow sample

## Labelling question

How was Cellpose used in this paper?

## Allowed labels

`inside_fiji`, `mention_only`, `other_pipeline`, `separate_elsewhere`, `separate_fiji_measure`, `separate_fiji_other`, `unclear`

## Inputs

The annotation bundle gives the identifier, the tool and the text.
For abstract-based sets that is the title and abstract; for full-text sets it is the
Methods mention windows and a full-text excerpt around the tool name. No pattern or
classifier result is shown.

## Provenance

Reconstructed from the existing label files, `data/validation/README.md`
and the manuscript Methods sections (Validation samples; Host-platform co-mentions and
the Cellpose sample; Reporting audit). Two independent annotators label each replicate.

