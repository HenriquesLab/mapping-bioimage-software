# Annotator provenance

Two independent language-model annotators labelled every validation item. The code refers to them by the aliases in `census.validation.label_replicates.ANNOTATORS`. This file records the model behind each alias. Where a run did not record an identifier, the table says so.

All runs went through child agents of the Pi coding harness. Each annotator received the same prompt batch and answered without seeing the other annotator's labels or the query or classifier result. The question wording and label categories are in `census.validation.label_replicates` (first round) and `census.validation.label_round2` (second round). The prompt batches and raw responses are gitignored working files under `data/raw/annotation/`.

| Check | Round | Alias | Model identifier | Labels committed |
|---|---|---|---|---|
| Registry aliases and microscope-control use (`alias`) | first | `deepseek` | `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash` | 77e6e66, 2026-10-06 |
| | first | `glm` | `synthetic/hf:zai-org/GLM-5.3-Flash` | 77e6e66, 2026-10-06 |
| Deep-learning vocabulary (`lexicon`) | first | `deepseek` | `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash` | 77e6e66, 2026-10-06 |
| | first | `glm` | `synthetic/hf:zai-org/GLM-5.3-Flash` | 77e6e66, 2026-10-06 |
| Research-area keywords (`domains`) | first and second | `deepseek` | `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash` | 77e6e66 (first), bf67bcf (second), 2026-10-06/07 |
| | first and second | `glm` | `synthetic/hf:zai-org/GLM-5.3-Flash` | 77e6e66 (first), bf67bcf (second), 2026-10-06/07 |
| Cellpose workflow (`cellpose`) | first and second | `deepseek` | `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash` | 77e6e66 (first), bf67bcf (second), 2026-10-06/07 |
| | first and second | `glm` | `synthetic/hf:zai-org/GLM-5.3-Flash` | 77e6e66 (first), bf67bcf (second), 2026-10-06/07 |
| StarDist and ilastik workflow (`workflow_hosts.py`) | second-round question | `deepseek` | `synthetic/hf:deepseek-ai/DeepSeek-V4.1-Flash` | 2026-10-14 |
| | second-round question | `glm` | `synthetic/hf:zai-org/GLM-5.3-Flash` | 2026-10-14 |
| Reporting-audit text patterns (`reporting`) | replicate 1 | `syn` | `synthetic/syn:large:text`, a routed alias of the Synthetic provider; the model it resolved to was not recorded | a3ddb06, 2026-10-06 |
| | replicate 1 | `gemini` | a Gemini 3.8 Flash model; the provider route was not recorded | a3ddb06, 2026-10-06 |
| | replicates 2 and 3 | `syn` | as replicate 1 | 77e6e66, 2026-10-06 |
| | replicates 2 and 3 | `gemini` | as replicate 1 | 77e6e66, 2026-10-06 |

The single-annotator labels kept in `data/validation/*.csv` from before the replicate design (alias precision, deep-learning vocabulary, research-area keywords, Cellpose workflow) do not record their annotator. The manuscript reports none of their numbers.

Future runs should record the resolved model identifier in each batch manifest, which removes the gaps above.
