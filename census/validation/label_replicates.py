"""Create, collect and score the first-round validation labels.

    python -m census.validation.label_replicates batches
    python -m census.validation.label_replicates collect
    python -m census.validation.label_replicates score

`batches` reads the annotation bundles created by
`census.validation.replicates validation` under `data/raw/annotation/`, then
writes prompt batches and a manifest under `data/raw/annotation/batches/`. The two independent annotators
work from the text supplied in each batch, blind to the query result. Their
aliases are defined in `ANNOTATORS`. Running the prompts uses a manual hand-off
through an external agent harness. `collect` validates responses and writes
label CSVs under `data/validation/replicates/`. `score` reports agreement for
each check and replicate. Only matching labels contribute to pooled summaries.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from census._paths import DATA_DIR, PROCESSED_DIR, RAW_DIR  # noqa: E402
from census._registry import load_registry  # noqa: E402

ANN = RAW_DIR / 'annotation'
BATCH = ANN / 'batches'
VAL = DATA_DIR / 'validation' / 'replicates'
OUT = PROCESSED_DIR / 'replicates'
MAX_CHARS = 30000
SETS = {
    'cellpose_workflow_2025': 'cellpose',
    'alias_precision_2025': 'alias',
    'alias_precision_core_2025': 'alias',
    'dl_lexicon_2021_2025': 'lexicon',
    'domain_keywords_2021_2025': 'domains',
    'reporting_audit_patterns_2025': 'reporting',
}
# Aliases only; data/validation/ANNOTATORS.md records the model behind each alias.
ANNOTATORS = {
    'cellpose': ('deepseek', 'glm'), 'alias': ('deepseek', 'glm'), 'lexicon': ('deepseek', 'glm'),
    'domains': ('deepseek', 'glm'), 'reporting': ('syn', 'gemini'),
}
FIELDS = {
    'cellpose': [('workflow', {'inside_fiji', 'separate_fiji_measure', 'separate_fiji_other',
                               'separate_elsewhere', 'other_pipeline', 'unclear', 'mention_only'})],
    'alias': [('sense', {'software', 'other_sense', 'not_found'}),
              ('use', {'acquisition', 'analysis', 'unclear', 'na'})],
    'lexicon': [('label', {'deep_learning', 'not_deep_learning', 'unclear'})],
    'domains': [('label', {'in_area', 'other_sense'})],
    'reporting': [(k, {'0', '1'}) for k in ('version', 'function', 'parameter', 'code')],
}

COMMON = ("Label each ITEM below from the text given only. Do not use tools. Do not explain.\n"
          "OUTPUT: one line per item, in the order given, exactly in the format shown, "
          "with no header, no other text and no code fences.\n")
INSTRUCTIONS = {
    'cellpose': COMMON + (
        "Each item is an open-access 2025 paper that names both Cellpose and ImageJ/Fiji. Decide how "
        "the paper used Cellpose, using exactly one label:\n"
        "inside_fiji = Cellpose was run inside Fiji/ImageJ (for example TrackMate-Cellpose or a Fiji plugin or wrapper).\n"
        "separate_fiji_measure = Cellpose was run on its own (its GUI, Python or command line) and its masks or "
        "regions of interest were then measured or analysed in Fiji/ImageJ.\n"
        "separate_fiji_other = Cellpose was run on its own and Fiji/ImageJ was used for a different step "
        "(for example preprocessing, visualisation or unrelated measurements).\n"
        "separate_elsewhere = Cellpose was run on its own and its output was measured in other software or "
        "the paper does not say where.\n"
        "other_pipeline = Cellpose was run inside other software (for example napari, QuPath, CellProfiler, "
        "a vendor platform or a published pipeline).\n"
        "unclear = Cellpose was used but the text does not say how it relates to Fiji/ImageJ.\n"
        "mention_only = Cellpose is named (for example cited or compared) without being used.\n"
        "FORMAT: item_id,label"),
    'alias': COMMON + (
        "Each item is a 2025 paper matched by a software name. Give two labels.\n"
        "sense: software = the matched name refers to the named software package; other_sense = the name "
        "means something else (a place, a person, a gene, an ordinary word); not_found = the name does not "
        "appear in the text given.\n"
        "use: only when the item says 'acquisition suite: yes' and sense is software: acquisition = the program "
        "was used only to run the microscope or acquire images; analysis = it was used to process, measure or "
        "analyse images; unclear = the text does not say. Use na in all other cases.\n"
        "FORMAT: item_id,sense,use"),
    'lexicon': COMMON + (
        "Each item is a title and abstract. Does the work report using or developing a deep-learning method "
        "(for example convolutional or other deep neural networks, U-Net, transformers, Cellpose, StarDist, "
        "or deep-learning-based segmentation or classification)?\n"
        "Write exactly one of these three words as the label: deep_learning (the work uses or develops a "
        "deep-learning method), not_deep_learning (it does not; classical machine learning such as random "
        "forests or support vector machines also counts as not_deep_learning), unclear (the abstract does not "
        "allow a decision). Never write yes or no.\n"
        "FORMAT: item_id,label (for example imagej|2022|36399578,not_deep_learning)"),
    'domains': COMMON + (
        "Each item gives a research area and a title and abstract. Is the paper's research in that area?\n"
        "in_area = the study's subject belongs to the named research area; other_sense = the area's terms "
        "appear only in passing, as a method or background, or in another meaning.\n"
        "Areas: Neuroscience; Cancer; Immunology; Microbiology and infection; Development and organoids; "
        "Plant biology; Organelles and cytoskeleton; Clinical and pathology (patients, clinical samples, "
        "biopsies, histopathology); Single-cell and spatial omics; Cardiovascular and renal; Metabolic disease "
        "and liver; Electron microscopy (the study uses or develops electron microscopy); Materials science; "
        "Computational methods (the paper develops or substantially describes computational or software methods).\n"
        "FORMAT: item_id,label"),
    'reporting': COMMON + (
        "For each ITEM, label four indicators as 1 (present) or 0 (absent) for the named TOOL.\n"
        "version = 1 if the Methods sentences state a version number of THIS tool (for example Fiji 2.14.0, "
        "ImageJ 1.54f, QuPath v0.5.1, CellProfiler 4.2.6, Cellpose 3, napari 0.4.19). A version of a different "
        "program or a citation alone does not count.\n"
        "function = 1 if the Methods sentences name the specific plugin, command, module, model or pretrained "
        "network used within this tool (for example Analyze Particles, TrackMate, Coloc 2, positive cell "
        "detection, pixel classifier, IdentifyPrimaryObjects, cyto3, nuclei model, 2D_versatile_fluo, a named "
        "napari plugin). Generic phrases (a custom macro, the plugin, deep learning) do not count. Naming "
        "another tool that runs inside this one counts.\n"
        "parameter = 1 if the Methods sentences give at least one parameter value used with this tool, name the "
        "thresholding method (for example Otsu), or state that default settings were used.\n"
        "code = 1 if the article states that analysis code, scripts, macros, notebooks or pipeline files are "
        "shared (a code-hosting link, a named script or pipeline file in the supplement or a repository, or a "
        "statement that code is publicly available). Available on request is 0. A data-only deposit is 0.\n"
        "FORMAT: item_id,version,function,parameter,code"),
}


def _clip(s, n):
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n] + ' [...]'


def _item(command, obj, acq):
    if command == 'reporting':
        iid = obj['item_id']
        mentions = '\n'.join(f'[{i + 1}] {_clip(w, 700)}' for i, w in enumerate(obj.get('methods_mentions') or []))
        text = (f"TOOL: {obj['tool_id']}\nMETHODS SENTENCES NAMING THE TOOL:\n{mentions or '(none)'}\n"
                f"CODE-RELATED STATEMENTS:\n{_clip(obj.get('code_context') or '(none found)', 3000)}")
        return iid, text
    ident = str(obj.get('identifier'))
    tool = obj['tool_id']
    stratum = str(obj.get('stratum'))
    if command == 'lexicon':
        iid = f'{tool}|{obj.get("year")}|{ident}'
        return iid, f"TITLE: {_clip(obj.get('title'), 400)}\nABSTRACT: {_clip(obj.get('abstract'), 3000)}"
    if command == 'domains':
        iid = f'{stratum}|{tool}|{ident}'
        return iid, (f"RESEARCH AREA: {stratum}\nTITLE: {_clip(obj.get('title'), 400)}\n"
                     f"ABSTRACT: {_clip(obj.get('abstract'), 3000)}")
    texts = obj.get('texts') or {}
    wins = list(texts.get('methods_mentions') or [])
    for w in texts.get('body_windows') or []:
        if w not in wins:
            wins.append(w)
    if command == 'alias':
        iid = f'{tool}|{ident}'
        body = '\n'.join(f'[{i + 1}] {_clip(w, 600)}' for i, w in enumerate(wins[:6]))
        return iid, (f"SOFTWARE NAME: {tool}\nACQUISITION SUITE: {'yes' if acq.get(tool) else 'no'}\n"
                     f"SENTENCES MATCHING THE NAME:\n{body or '(no sentence found in the full text)'}")
    iid = f'cellpose|{ident}'
    body = '\n'.join(f'[{i + 1}] {_clip(w, 700)}' for i, w in enumerate(wins[:12]))
    return iid, f"SENTENCES NAMING CELLPOSE, IMAGEJ OR FIJI:\n{body or '(full text unavailable)'}"


def batches():
    reg = load_registry()
    acq = {t.id: t.category == 'acquisition-suite' for t in reg.tools}
    BATCH.mkdir(parents=True, exist_ok=True)
    for f in BATCH.glob('*.txt'):
        if '.' not in f.stem:
            f.unlink()
    manifest = []
    for name, command in SETS.items():
        for rep in (1, 2, 3):
            src = ANN / f'{name}_r{rep}.jsonl'
            items = [_item(command, json.loads(l), acq) for l in src.read_text().splitlines() if l.strip()]
            ids = [i for i, _ in items]
            assert len(ids) == len(set(ids)), f'duplicate item ids in {src.name}'
            chunk, size, k = [], 0, 0
            for iid, text in items + [(None, None)]:
                block = None if iid is None else f'### ITEM {iid}\n{text}\n'
                if chunk and (iid is None or size + len(block) > MAX_CHARS):
                    k += 1
                    bid = f'{name}_r{rep}_b{k:02d}'
                    (BATCH / f'{bid}.txt').write_text(''.join(b for _, b in chunk))
                    manifest.append(dict(batch=bid, set=name, command=command, replicate=rep,
                                         items=[i for i, _ in chunk], chars=size))
                    chunk, size = [], 0
                if iid is not None:
                    chunk.append((iid, block))
                    size += len(block)
    (BATCH / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    (BATCH / 'instructions.json').write_text(json.dumps(INSTRUCTIONS, indent=1))
    print(f'wrote {len(manifest)} batches')


def _parse(command, text, expected):
    fields = FIELDS[command]
    want = set(expected)
    got = {}
    for line in text.splitlines():
        line = line.strip().strip('`').strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 1 + len(fields) or parts[0] not in want:
            continue
        vals = parts[1:]
        if all(v in allowed for v, (_, allowed) in zip(vals, fields)):
            got[parts[0]] = vals
    return got


def collect():
    manifest = json.loads((BATCH / 'manifest.json').read_text())
    VAL.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, command in SETS.items():
        for ann in ANNOTATORS[command]:
            for rep in (1, 2, 3):
                if command == 'reporting' and rep == 1:
                    continue  # replicate 1 keeps the original labels
                rows = []
                for b in (m for m in manifest if m['set'] == name and m['replicate'] == rep):
                    ans = BATCH / f"{b['batch']}.{ann}.txt"
                    got = _parse(command, ans.read_text(), b['items']) if ans.exists() else {}
                    for iid in b['items']:
                        if iid in got:
                            rows.append([iid] + got[iid])
                        else:
                            missing.append((b['batch'], ann, iid))
                cols = ['item_id'] + [f for f, _ in FIELDS[command]]
                pd.DataFrame(rows, columns=cols).to_csv(VAL / f'{name}_labels_{ann}_r{rep}.csv', index=False)
    by = Counter((b, a) for b, a, _ in missing)
    (BATCH / 'missing.json').write_text(json.dumps([dict(batch=b, annotator=a, n=n) for (b, a), n in by.items()], indent=1))
    print(f'missing labels: {len(missing)} in {len(by)} batch-annotator pairs')


def _kappa(a, b):
    cats = sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return float('nan')
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((list(a).count(c) / n) * (list(b).count(c) / n) for c in cats)
    return float('nan') if pe == 1 else (po - pe) / (1 - pe)


def score():
    rows = []
    for name, command in SETS.items():
        a1, a2 = ANNOTATORS[command]
        for rep in (1, 2, 3):
            if command == 'reporting' and rep == 1:
                f1 = DATA_DIR / 'validation' / 'reporting_audit_labels_syn.csv'
                f2 = DATA_DIR / 'validation' / 'reporting_audit_labels_gemini.csv'
            else:
                f1 = VAL / f'{name}_labels_{a1}_r{rep}.csv'
                f2 = VAL / f'{name}_labels_{a2}_r{rep}.csv'
            if not (f1.exists() and f2.exists()):
                continue
            x = pd.read_csv(f1, dtype=str).set_index('item_id')
            y = pd.read_csv(f2, dtype=str).set_index('item_id')
            common = x.index.intersection(y.index)
            for field, _ in FIELDS[command]:
                if field not in x.columns:
                    continue
                u, v = x.loc[common, field], y.loc[common, field]
                agree = (u == v)
                rec = dict(set=name, replicate=rep, field=field, items=len(common),
                           agreement_pct=round(100 * agree.mean(), 1), kappa=round(_kappa(list(u), list(v)), 2))
                cons = u[agree]
                if command == 'lexicon':
                    strata = {iid: s for iid, s in _lexicon_strata(rep).items()}
                    pos = [iid for iid in cons.index if strata.get(iid) == 'lex_pos']
                    neg = [iid for iid in cons.index if strata.get(iid) == 'lex_neg']
                    rec.update(lex_pos_agreed=len(pos), lex_pos_dl=int(sum(cons[i] == 'deep_learning' for i in pos)),
                               lex_neg_agreed=len(neg), lex_neg_dl=int(sum(cons[i] == 'deep_learning' for i in neg)))
                elif command == 'domains':
                    rec.update(agreed=len(cons), in_area=int((cons == 'in_area').sum()))
                elif command == 'alias' and field == 'sense':
                    rec.update(agreed=len(cons), software=int((cons == 'software').sum()))
                elif command == 'cellpose':
                    rec.update(agreed=len(cons), **{f'n_{k}': int(c) for k, c in cons.value_counts().items()})
                rows.append(rec)
    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / 'validation_replicates.csv', index=False)
    print(out.to_string(index=False))


def _lexicon_strata(rep):
    src = VAL / f'dl_lexicon_2021_2025_items_r{rep}.csv'
    items = pd.read_csv(src, dtype=str).fillna('')
    return {
        f'{row.tool_id}|{row.year}|{row.epmc_id or row.pmcid}': row.stratum
        for row in items.itertuples(index=False)
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = {
        'batches': (batches, 'Write prompt batches for both annotators.'),
        'collect': (collect, 'Collect annotator responses into label CSVs.'),
        'score': (score, 'Report agreement and validation metrics per check.'),
    }
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name, (handler, help_text) in commands.items():
        subparsers.add_parser(name, help=help_text).set_defaults(handler=handler)
    args = parser.parse_args(argv)
    args.handler()


if __name__ == '__main__':
    main()
