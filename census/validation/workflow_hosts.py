"""How StarDist and ilastik were run in papers that also mention ImageJ/Fiji, 2025.

Same design as the Cellpose workflow sample (label_round2, set cellpose_workflow_2025):
the frame is the open-access 2025 full-text microscopy papers mentioning the method
and ImageJ/Fiji; three disjoint seeded draws of 40 (census thirds for small frames);
two annotators label each paper's Methods text with the round-two Cellpose question,
with the method's name and Fiji integrations swapped in.

    python -m census.validation.workflow_hosts draw      # frames, items, full text, batches
    python -m census.validation.workflow_hosts collect   # annotator answers -> label CSVs
    python -m census.validation.workflow_hosts pooled    # agreed labels per replicate and pooled

Annotator answers are written next to each batch as <batch>.deepseek.txt and
<batch>.glm.txt by the Pi harness (data/validation/ANNOTATORS.md).
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from census._registry import build_boolean_query, load_registry
from census.build import build_reporting_audit as ba
from census.validation import label_replicates as L
from census.validation.label_round2 import _methods_text
from census.validation.replicates import RAW_DIR, VAL_OUT, atomic_json, draw_replicates

SEED = '20261014-workflow-hosts-v1'
N = 40
BATCH = L.ANN / 'batches_hosts'
MAX_CHARS = 30000
CATS = ['separate', 'inside_fiji', 'other_pipeline', 'unclear', 'mention_only']
COLUMNS = ['stratum', 'tool_id', 'year', 'epmc_id', 'pmcid']
# name in the prompt, search terms for the Methods excerpt, Fiji integrations named in the label definition
METHODS = {
    'stardist': ('StarDist', 'stardist|imagej|fiji', 'the StarDist Fiji plugin or TrackMate-StarDist'),
    'ilastik': ('ilastik', 'ilastik|imagej|fiji', 'the ilastik Fiji plugin'),
}


def name(method: str) -> str:
    return f'{method}_workflow_2025'


def instructions(method: str) -> str:
    label, _, fiji = METHODS[method]
    return L.COMMON + (
        f"Each item is an open-access 2025 paper that names both {label} and ImageJ/Fiji; you see its Methods "
        f"text. Decide how the paper combined {label} with Fiji/ImageJ, using exactly one label:\n"
        f"inside_fiji = {label} was run inside Fiji/ImageJ (for example {fiji}).\n"
        f"separate = {label} was run on its own (its own interface, Python or command line) and the text states "
        f"what was done with its output afterwards, in Fiji/ImageJ or elsewhere.\n"
        f"unclear = both programs are used but the text does not say how {label} and Fiji/ImageJ were combined or "
        f"what happened to the {label} output.\n"
        f"other_pipeline = {label} was run inside other software (for example napari, QuPath, CellProfiler, a vendor "
        f"platform or a published pipeline).\n"
        f"mention_only = {label} is named (for example cited or compared) without being used.\n"
        "Write exactly one of these five words as the label.\n"
        f"FORMAT: item_id,label (for example {method}|PMC12385590,separate)")


def draw() -> None:
    reg = load_registry()
    ij = build_boolean_query(reg.by_id('imagej'), '')
    BATCH.mkdir(parents=True, exist_ok=True)
    manifest, prompts = [], {}
    for method in METHODS:
        q = f"{build_boolean_query(reg.by_id(method), reg.context_query)} AND {ij} AND OPEN_ACCESS:Y AND PUB_YEAR:2025"
        pmcids = sorted(set(ba.frame_pmcids(q)))
        units = [dict(stratum=method, tool_id=method, year='2025', epmc_id='', pmcid=p) for p in pmcids]
        parts = draw_replicates(units, N, seed=f'{SEED}-{method}')
        frames = RAW_DIR / 'validation_frames'
        frames.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(units, columns=COLUMNS).to_csv(frames / f'{name(method)}_frame.csv', index=False)
        atomic_json(frames / f'{name(method)}_frame.json', dict(query=q, frame_unit='pmcid'))
        atomic_json(VAL_OUT / f'{name(method)}_design.json', dict(
            name=name(method), command='workflow', seed=f'{SEED}-{method}', population=len(pmcids),
            replicate_sizes=[len(p) for p in parts], census=len(pmcids) < 3 * N,
            note='Same design as cellpose_workflow_2025. Replicates are disjoint.'))
        prompts[method] = instructions(method)
        for rep, part in enumerate(parts, 1):
            pd.DataFrame(part)[COLUMNS].to_csv(VAL_OUT / f'{name(method)}_items_r{rep}.csv', index=False)
            items = []
            for u in part:
                ba.fetch_xml(u['pmcid'])
                items.append((f"{method}|{u['pmcid']}", f"METHODS TEXT:\n{_methods_text(u['pmcid'], terms=METHODS[method][1])}"))
            chunk, size, k = [], 0, 0
            for iid, text in items + [(None, None)]:
                block = None if iid is None else f'### ITEM {iid}\n{text}\n'
                if chunk and (iid is None or size + len(block) > MAX_CHARS):
                    k += 1
                    bid = f'{name(method)}_r{rep}_b{k:02d}'
                    (BATCH / f'{bid}.txt').write_text(''.join(b for _, b in chunk))
                    manifest.append(dict(batch=bid, method=method, replicate=rep, items=[i for i, _ in chunk], chars=size))
                    chunk, size = [], 0
                if iid is not None:
                    chunk.append((iid, block))
                    size += len(block)
        print(f'{method}: frame {len(pmcids)}, drawn {[len(p) for p in parts]}', flush=True)
    (BATCH / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    (BATCH / 'instructions.json').write_text(json.dumps(prompts, indent=1))
    print(f'wrote {len(manifest)} batches')


def collect() -> None:
    manifest = json.loads((BATCH / 'manifest.json').read_text())
    missing = 0
    for method in METHODS:
        for ann in ('deepseek', 'glm'):
            for rep in (1, 2, 3):
                rows = []
                for b in (m for m in manifest if m['method'] == method and m['replicate'] == rep):
                    ans = BATCH / f"{b['batch']}.{ann}.txt"
                    want, got = set(b['items']), {}
                    for line in (ans.read_text() if ans.exists() else '').splitlines():
                        parts = [p.strip() for p in line.strip().strip('`').split(',')]
                        if len(parts) == 2 and parts[0] in want and parts[1] in CATS:
                            got[parts[0]] = parts[1]
                    missing += len(want) - len(got)
                    rows += [[i, got[i]] for i in b['items'] if i in got]
                pd.DataFrame(rows, columns=['item_id', 'workflow']).to_csv(
                    L.VAL / f'{name(method)}_labels_{ann}_r{rep}_v2.csv', index=False)
    print('missing labels:', missing)


def pooled() -> None:
    """Agreed labels per replicate and pooled, in the format of cellpose_workflow_pooled_2025.csv."""
    for method in METHODS:
        rows = {c: {} for c in CATS + ['agreed', 'labelled']}
        for rep in (1, 2, 3):
            a = pd.read_csv(L.VAL / f'{name(method)}_labels_deepseek_r{rep}_v2.csv').set_index('item_id').workflow
            b = pd.read_csv(L.VAL / f'{name(method)}_labels_glm_r{rep}_v2.csv').set_index('item_id').workflow
            common = a.index.intersection(b.index)
            cons = a.loc[common][a.loc[common] == b.loc[common]]
            for c in CATS:
                rows[c][f'r{rep}'] = int((cons == c).sum())
            rows['agreed'][f'r{rep}'] = len(cons)
            rows['labelled'][f'r{rep}'] = len(common)
        out = pd.DataFrame(rows).T[['r1', 'r2', 'r3']]
        out['pooled'] = out.sum(axis=1)
        out.index.name = 'category'
        out.to_csv(L.PROCESSED_DIR / f'{name(method)}_pooled.csv')
        print(method)
        print(out.to_string())


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('step', choices=['draw', 'collect', 'pooled'])
    {'draw': draw, 'collect': collect, 'pooled': pooled}[p.parse_args().step]()
