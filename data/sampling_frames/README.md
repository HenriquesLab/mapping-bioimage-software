# Frozen sampling frames

Identifier-only outputs of `python -m census.build.build_sampling_frames`.
Tool-year frames preserve cached response order; audit PMCIDs are sorted and unique.
Validation frames retain identifiers, strata and portable source metadata.
No network requests are made. `metadata.json` records queries, cache checksums,
population drift and completeness. Incomplete frames limit exact reproduction.

## Known incomplete frames

- `data/sampling_frames/tool_year/imagej_2017.csv`: cached hitCount 18414, recovered 18415 records
- `data/sampling_frames/tool_year/imagej_2019.csv`: cached hitCount 24258, recovered 24259 records
- `data/sampling_frames/tool_year/imagej_2020.csv`: cached hitCount 29768, recovered 29769 records
- `data/sampling_frames/tool_year/imagej_2021.csv`: cached hitCount 36120, recovered 36121 records
- `data/sampling_frames/tool_year/imagej_2022.csv`: cached hitCount 39482, recovered 39483 records
- `data/sampling_frames/tool_year/imagej_2024.csv`: cached hitCount 39399, recovered 39397 records
- `data/sampling_frames/tool_year/imagej_2025.csv`: cached hitCount 49255, recovered 49257 records
- `data/sampling_frames/tool_year/matlab_2017.csv`: cached hitCount 4658, recovered 4659 records
