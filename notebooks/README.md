# Reproduce the paper figures and tables

These ten notebooks render every panel of the nine publication figures and build all 14 supplementary tables from committed data. They run offline in a standalone clone and in the manuscript repository's `scripts/` checkout. They do not need article text or raw API caches. The main text contains no tables.

## Coverage map

Figure targets use the manuscript PNG stem. Each figure notebook ends with **Render all panels** and **Check against the manuscript**. The latter compares every full-resolution RGBA pixel when `../MANUSCRIPT/FIGURES/<stem>.png` exists. It prints a skip note when the manuscript is absent in a public clone.

| Target | Notebook | Section and output |
| --- | --- | --- |
| Figure1__overview | [Figure1.ipynb](Figure1.ipynb) | Reconstruct panel quantities; Render all panels, a-c |
| Figure2__landscape | [Figure2.ipynb](Figure2.ipynb) | Reconstruct panel quantities; Render all panels, all three columns |
| Figure3__citations | [Figure3.ipynb](Figure3.ipynb) | Citation queries for panels a-b; Reconstruct panel quantities; Render all panels, a-b |
| Figure4__reach | [Figure4.ipynb](Figure4.ipynb) | Reconstruct panel quantities; Render all panels, a-b |
| Figure5__domains | [Figure5.ipynb](Figure5.ipynb) | Reconstruct panel quantities; Render all panels, complete matrix |
| Figure6__deep_learning | [Figure6.ipynb](Figure6.ipynb) | Reconstruct panel quantities; Render all panels, a-d |
| SFigure1__trajectories | [SFigure1.ipynb](SFigure1.ipynb) | Reconstruct panel quantities; Render all panels, all 30 package trajectories |
| SFigure2__terms | [SFigure2.ipynb](SFigure2.ipynb) | Reconstruct panel quantities; Render all panels, a-h |
| SFigure3__triangulation | [SFigure3.ipynb](SFigure3.ipynb) | Reconstruct panel quantities; Render all panels, a-c and label column |
| registry | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | registry |
| literature | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | literature |
| deep_learning | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | deep_learning |
| methods_section | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | methods_section |
| methods_micro | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | methods_micro |
| validation | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | validation |
| mesh | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | mesh |
| reporting | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | reporting |
| audit_area | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | audit_area |
| adoption | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | adoption |
| wildcard | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | wildcard |
| queryerrors | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | queryerrors |
| citations | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | citations |
| preprints | [SupplementaryTables.ipynb](SupplementaryTables.ipynb) | preprints |

The manuscript working folder also contains two historical PNGs which the current paper does not reference. They are outside the publication targets. The corresponding notebooks identify them under **Historical variant**:

| Historical file | Notebook documenting its status | Section |
| --- | --- | --- |
| Figure3_new_DL_in_tools | [Figure3.ipynb](Figure3.ipynb) | Historical variant, superseded by the current citation figure |
| Figure4_new_dlwithintool | [Figure4.ipynb](Figure4.ipynb) | Historical variant, superseded by the current reach figure |

## Run the notebooks

From the repository root, create a Python 3.11 environment and install the pinned renderer and notebook dependencies. Installation needs network access unless the packages are cached. Execution uses committed local files only.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-notebooks.txt
.venv/bin/python -m ipykernel install --sys-prefix --name bioimage-figures --display-name 'Bioimage figures'
```

Execute each notebook with the environment's kernel explicitly selected. This also avoids selecting a different user-level kernel with the same name.

```sh
for notebook in notebooks/*.ipynb; do
  JUPYTER_PREFER_ENV_PATH=1 .venv/bin/jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=bioimage-figures \
    --ExecutePreprocessor.timeout=600 "$notebook" || break
done
```

For interactive use, start `.venv/bin/jupyter lab`, open a notebook and choose the environment's Python kernel. Paths resolve from the notebook directory upwards. Rendered images use temporary directories; the notebooks never overwrite manuscript images or derived data. Each figure keeps a scaled preview and prints a full-size pixel hash. Font availability and renderer versions affect exact image comparisons; the requirements pin Matplotlib 3.11.2, and the manuscript renderer uses Arial when installed.

The table notebook calls the same `census.tables.make_si_tables.TABLES` functions as the pipeline. It displays each table and asserts equality with the corresponding `TABLE:<name>` block when the SI file exists. A public clone prints a comparison skip note for the absent manuscript.

## Documentation and rebuilding

Every notebook includes a title and summary, an **Inputs** table with file contents and producer modules, panel or table explanations before code, **Rebuilding from scratch**, and a closing manuscript check.

Figure 3 uses `data/citation_reference_metadata.json` for indexed reference identifiers and publication years. S2 uses `data/sfigure2_terms.csv` for its 64 aggregate term rows. Figures 5 and 6 use committed area and vocabulary estimates. These inputs contain no article text. Their notebook rebuild notes explain the relevant producer functions.

Rebuilding sampled text requires network access through `python release/refetch_identifiers.py`. Classification, term aggregation, validation pooling and plotting can then run locally. Source-count collectors need network access when raw caches are absent. The default notebook cells never run those collectors. Repository-star and download snapshots describe their original collection date.

## Checks

```sh
python -m pytest -q tests/test_notebooks_cover_outputs.py
python -m pytest -q
```

In a manuscript checkout, run `python tools/check_numbers.py` from the parent repository. `tests/test_notebooks_cover_outputs.py` checks the figure stems and SI table names against this map and the notebooks, documentation sections, and the two aggregate-input renderer contracts. Public-clone execution checks also verify that no raw cache pages appear and that notebook outputs contain no machine-specific `/Users/` paths.
