# Rubric: Cellpose workflow, human labels (replicate 1)

One reader labels the 40 papers in `cellpose_workflow_2025_human_r1.csv` (the same papers as `cellpose_workflow_2025_items_r1.csv`) by reading each paper's full text in Europe PMC (`https://europepmc.org/article/PMC/<pmcid>`). Do not look at the model labels in this folder before finishing; the point is an independent check of them.

## Question

How did this paper run Cellpose, and how did Cellpose relate to Fiji/ImageJ in the workflow?

## Labels (one per paper)

| Label | Use when | Manuscript category |
|---|---|---|
| `inside_fiji` | Cellpose ran from within Fiji (for example TrackMate-Cellpose, a BIOP wrapper or a Fiji macro calling Cellpose) | inside Fiji |
| `separate_fiji_downstream_measure` | Cellpose ran on its own; its masks or ROIs went to Fiji for measurement | ran on its own |
| `separate_fiji_downstream_track` | Cellpose ran on its own; its output went to Fiji for tracking (for example TrackMate) | ran on its own |
| `separate_fiji_downstream_other` | Cellpose ran on its own; its output went to Fiji for another step (post-processing, editing, skeletonising) | ran on its own |
| `separate_fiji_upstream` | Fiji prepared images before Cellpose; Cellpose output was analysed elsewhere | ran on its own |
| `separate_fiji_upstream_downstream` | Fiji both prepared images for Cellpose and analysed its output | ran on its own |
| `separate_fiji_elsewhere` | Cellpose ran on its own; Fiji was used in the paper for an unrelated task (blots, figure contrast, other images) | ran on its own |
| `separate_elsewhere` | Cellpose ran on its own; its output was analysed in Python, CellProfiler or another program, and Fiji's role is not stated | ran on its own |
| `other_pipeline` | Cellpose ran inside another program or pipeline (for example napari, QuPath, a vendor or spatial-omics pipeline) | inside other software |
| `unclear` | The paper uses Cellpose but the text does not say how it was run or how it related to Fiji; give the reason in `note` | combination not stated |
| `mention_only` | Cellpose is named without being used (review, comparison, list of compatible tools) | named only |

## Notes column

Write a short note in your own words (for example "masks to Fiji for area and mean intensity"). Do not paste sentences from the paper: article text stays under the publisher's copyright and cannot go in the repository. Avoid commas in the note, or keep the default CSV quoting your spreadsheet applies.
