"""Run the second annotation round for Cellpose workflow and research areas.

    python -m census.validation.label_round2 batches
    python -m census.validation.label_round2 collect
    python -m census.validation.label_round2 score
    python -m census.validation.label_round2 pooled

Round two repeats the original questions for Cellpose workflow and research-
area keywords. Cellpose batches include Methods text. Area batches include the
matched keyword and its sentence. Batch generation and response collection use
a manual hand-off through an external agent harness. `pooled` rebuilds the
Cellpose, validation and area-precision outputs from collected labels. The
`ROUND_FOR_AREA` setting scores Electron microscopy on a third round asking about use of the technique.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from census.build import build_reporting_audit as ba  # noqa: E402
from census.validation import label_replicates as L  # noqa: E402
from census.figures.domains import DOMAINS  # noqa: E402

BATCH = L.ANN / 'batches_v2'
MAX_CHARS = 30000
SETS = {'cellpose_workflow_2025': 'cellpose', 'domain_keywords_2021_2025': 'domains'}
FIELDS = {
    'cellpose': [('workflow', {'inside_fiji', 'separate', 'unclear', 'other_pipeline', 'mention_only'})],
    'domains': [('label', {'in_area', 'other_sense'})],
}
INSTRUCTIONS = {
    'cellpose': L.COMMON + (
        "Each item is an open-access 2025 paper that names both Cellpose and ImageJ/Fiji; you see its Methods "
        "text. Decide how the paper combined Cellpose with Fiji/ImageJ, using exactly one label:\n"
        "inside_fiji = Cellpose was run inside Fiji/ImageJ (for example TrackMate-Cellpose or a Fiji plugin or wrapper).\n"
        "separate = Cellpose was run on its own (its GUI, Python or command line) and the text states what was done "
        "with its output afterwards, in Fiji/ImageJ or elsewhere.\n"
        "unclear = both programs are used but the text does not say how Cellpose and Fiji/ImageJ were combined or "
        "what happened to the Cellpose output.\n"
        "other_pipeline = Cellpose was run inside other software (for example napari, QuPath, CellProfiler, a vendor "
        "platform or a published pipeline).\n"
        "mention_only = Cellpose is named (for example cited or compared) without being used.\n"
        "Write exactly one of these five words as the label.\n"
        "FORMAT: item_id,label (for example cellpose|PMC12385590,separate)"),
    'domains': L.COMMON + (
        "Each item gives a research area, the keyword that matched it in the title or abstract, the sentence "
        "containing that keyword, and the title and abstract. Does the matched keyword mark this paper as "
        "research in that area?\n"
        "in_area = yes, the keyword reflects the paper's research topic in that area.\n"
        "other_sense = the keyword appears in passing (background, a method, a comparison) or in another meaning.\n"
        "Write exactly in_area or other_sense as the label, and copy each item_id exactly, including the \"|\" "
        "separators.\n"
        "FORMAT: item_id,label (for example Immunology|stardist|38274810,in_area)"),
}


def _methods_text(pmcid: str, limit: int = 9000, terms: str = 'cellpose|imagej|fiji') -> str:
    path = ba.XML_DIR / f'{pmcid}.xml'
    xml = path.read_text() if path.exists() else ''
    if not xml:
        return '(full text unavailable)'
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return '(full text unavailable)'
    ba._strip_citations(root)
    secs = ba.methods_sections(root)
    blocks = [b for s in secs for b in ba._blocks(s)] or ba._blocks(root.find('.//body') or root)
    hit = re.compile(f'(?i){terms}')
    keep = [b for b in blocks if hit.search(b)]
    rest = [b for b in blocks if not hit.search(b)]
    out, size = [], 0
    for b in keep + rest:
        if size + len(b) > limit:
            break
        out.append(b)
        size += len(b) + 1
    avail = [L._clip(ET.tostring(s, encoding='unicode', method='text'), 1200) for s in root.iter('sec')
             if 'availab' in (s.findtext('title') or '').lower()]
    return '\n'.join(out) + ('\nAVAILABILITY: ' + ' '.join(avail) if avail else '')


def _domain_match(area: str, title: str, abstract: str) -> tuple[str, str]:
    rx = re.compile(DOMAINS[area], re.I)
    text = f'{title}. {abstract}'
    m = rx.search(text)
    if not m:
        return '(no match found)', ''
    for sent in re.split(r'(?<=[.!?])\s+', text):
        if rx.search(sent):
            return m.group(0), L._clip(sent, 500)
    return m.group(0), ''


def _item(command, obj):
    ident, tool, stratum = str(obj.get('identifier')), obj['tool_id'], str(obj.get('stratum'))
    if command == 'cellpose':
        return f'cellpose|{ident}', f"METHODS TEXT:\n{_methods_text(ident)}"
    kw, sent = _domain_match(stratum, obj.get('title') or '', obj.get('abstract') or '')
    return f'{stratum}|{tool}|{ident}', (
        f"RESEARCH AREA: {stratum}\nMATCHED KEYWORD: {kw}\nSENTENCE: {sent}\n"
        f"TITLE: {L._clip(obj.get('title'), 400)}\nABSTRACT: {L._clip(obj.get('abstract'), 3000)}")


def batches():
    BATCH.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, command in SETS.items():
        for rep in (1, 2, 3):
            src = L.ANN / f'{name}_r{rep}.jsonl'
            items = [_item(command, json.loads(l)) for l in src.read_text().splitlines() if l.strip()]
            chunk, size, k = [], 0, 0
            for iid, text in items + [(None, None)]:
                block = None if iid is None else f'### ITEM {iid}\n{text}\n'
                if chunk and (iid is None or size + len(block) > MAX_CHARS):
                    k += 1
                    bid = f'{name}_r{rep}_v2_b{k:02d}'
                    (BATCH / f'{bid}.txt').write_text(''.join(b for _, b in chunk))
                    manifest.append(dict(batch=bid, set=name, command=command, replicate=rep,
                                         items=[i for i, _ in chunk], chars=size))
                    chunk, size = [], 0
                if iid is not None:
                    chunk.append((iid, block))
                    size += len(block)
    (BATCH / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    (BATCH / 'instructions.json').write_text(json.dumps(INSTRUCTIONS, indent=1))
    print(f'wrote {len(manifest)} batches', {n: sum(m['set'] == n for m in manifest) for n in SETS})


def collect():
    manifest = json.loads((BATCH / 'manifest.json').read_text())
    missing = 0
    for name, command in SETS.items():
        for ann in ('deepseek', 'glm'):
            for rep in (1, 2, 3):
                rows = []
                for b in (m for m in manifest if m['set'] == name and m['replicate'] == rep):
                    ans = BATCH / f"{b['batch']}.{ann}.txt"
                    fields = FIELDS[command]
                    want = set(b['items'])
                    got = {}
                    for line in (ans.read_text() if ans.exists() else '').splitlines():
                        parts = [p.strip() for p in line.strip().strip('`').split(',')]
                        if len(parts) == 2 and parts[0] in want and parts[1] in fields[0][1]:
                            got[parts[0]] = parts[1]
                    missing += len(want) - len(got)
                    rows += [[i, got[i]] for i in b['items'] if i in got]
                pd.DataFrame(rows, columns=['item_id', FIELDS[command][0][0]]).to_csv(
                    L.VAL / f'{name}_labels_{ann}_r{rep}_v2.csv', index=False)
    print('missing labels:', missing)


def score():
    rows = []
    for name, command in SETS.items():
        field = FIELDS[command][0][0]
        for rep in (1, 2, 3):
            a = pd.read_csv(L.VAL / f'{name}_labels_deepseek_r{rep}_v2.csv', dtype=str).set_index('item_id')[field]
            b = pd.read_csv(L.VAL / f'{name}_labels_glm_r{rep}_v2.csv', dtype=str).set_index('item_id')[field]
            common = a.index.intersection(b.index)
            u, v = a.loc[common], b.loc[common]
            cons = u[u == v]
            rec = dict(set=name, replicate=rep, items=len(common), agreement_pct=round(100 * (u == v).mean(), 1),
                       kappa=round(L._kappa(list(u), list(v)), 2), agreed=len(cons))
            rec.update({f'n_{k}': int(c) for k, c in cons.value_counts().items()})
            rows.append(rec)
    out = pd.DataFrame(rows).fillna(0)
    out.to_csv(L.OUT / 'validation_replicates_v2.csv', index=False)
    print(out.to_string(index=False))


def pooled_cellpose():
    """Agreed second-round Cellpose labels per replicate and pooled, for Figure 6d and the text."""
    cats = ['separate', 'inside_fiji', 'other_pipeline', 'unclear', 'mention_only']
    rows = {c: {} for c in cats + ['agreed', 'labelled']}
    for rep in (1, 2, 3):
        a = pd.read_csv(L.VAL / f'cellpose_workflow_2025_labels_deepseek_r{rep}_v2.csv').set_index('item_id').workflow
        b = pd.read_csv(L.VAL / f'cellpose_workflow_2025_labels_glm_r{rep}_v2.csv').set_index('item_id').workflow
        common = a.index.intersection(b.index)
        cons = a.loc[common][a.loc[common] == b.loc[common]]
        for c in cats:
            rows[c][f'r{rep}'] = int((cons == c).sum())
        rows['agreed'][f'r{rep}'] = len(cons)
        rows['labelled'][f'r{rep}'] = len(common)
    out = pd.DataFrame(rows).T[['r1', 'r2', 'r3']]
    out['pooled'] = out.sum(axis=1)
    out.index.name = 'category'
    dest = L.PROCESSED_DIR / 'cellpose_workflow_pooled_2025.csv'
    out.to_csv(dest)
    print(out.to_string())


def pooled_validation():
    """Agreed labels per replicate and pooled for the alias, lexicon and research-area checks."""
    from census._registry import load_registry
    acq = {t.id for t in load_registry().tools if t.category == 'acquisition-suite'}

    def agreed(name, field, rep, suffix=''):
        a = pd.read_csv(L.VAL / f'{name}_labels_deepseek_r{rep}{suffix}.csv', dtype=str).set_index('item_id')
        b = pd.read_csv(L.VAL / f'{name}_labels_glm_r{rep}{suffix}.csv', dtype=str).set_index('item_id')
        c = a.index.intersection(b.index)
        return a.loc[c][a.loc[c, field] == b.loc[c, field]], len(c)

    strata = {key: value for rep in (1, 2, 3)
              for key, value in L._lexicon_strata(rep).items()}
    m = {}
    for rep in (1, 2, 3):
        r = f'r{rep}'
        g, n = agreed('alias_precision_2025', 'sense', rep)
        m.setdefault('alias_labelled', {})[r] = n
        m.setdefault('alias_agreed', {})[r] = len(g)
        m.setdefault('alias_software', {})[r] = int((g.sense == 'software').sum())
        u, _ = agreed('alias_precision_2025', 'use', rep)
        u = u[u.index.str.split('|').str[0].isin(acq) & (u.sense == 'software')]
        m.setdefault('acq_agreed', {})[r] = len(u)
        for k in ('acquisition', 'analysis', 'unclear'):
            m.setdefault(f'acq_{k}', {})[r] = int((u.use == k).sum())
        g, n = agreed('dl_lexicon_2021_2025', 'label', rep)
        s = g.index.map(strata)
        pos, neg = g[s == 'lex_pos'], g[s == 'lex_neg']
        m.setdefault('lex_labelled', {})[r] = n
        m.setdefault('lex_pos_agreed', {})[r] = len(pos)
        m.setdefault('lex_pos_dl', {})[r] = int((pos.label == 'deep_learning').sum())
        m.setdefault('lex_neg_agreed', {})[r] = len(neg)
        m.setdefault('lex_neg_dl', {})[r] = int((neg.label == 'deep_learning').sum())
        g, n = agreed('domain_keywords_2021_2025', 'label', rep, '_v2')
        m.setdefault('dom_labelled', {})[r] = n
        m.setdefault('dom_agreed', {})[r] = len(g)
        m.setdefault('dom_in_area', {})[r] = int((g.label == 'in_area').sum())
    out = pd.DataFrame(m).T[['r1', 'r2', 'r3']]
    out['pooled'] = out.sum(axis=1)
    out.index.name = 'metric'
    out.to_csv(L.PROCESSED_DIR / 'validation_pooled_2025.csv')
    print(out.to_string())


# Electron microscopy is defined by use of the technique. The second-round question
# counted a keyword appearing "as a method" as a passing match, so this area is scored
# on a third round (suffix _em, 13 October 2026) that asked whether the study uses or
# develops electron microscopy, with the same evidence as round two.
ROUND_FOR_AREA = {'Electron microscopy': 'em'}
MIN_AREA_PRECISION = 0.5


def area_precision():
    """Per-area keyword precision from agreed labels pooled over three replicates."""
    def agreed(rep, suffix):
        a = pd.read_csv(L.VAL / f'domain_keywords_2021_2025_labels_deepseek_r{rep}{suffix}.csv', dtype=str).set_index('item_id')
        b = pd.read_csv(L.VAL / f'domain_keywords_2021_2025_labels_glm_r{rep}{suffix}.csv', dtype=str).set_index('item_id')
        c = a.index.intersection(b.index)
        g = a.loc[c][a.loc[c, 'label'] == b.loc[c, 'label']]
        return g.assign(area=g.index.str.split('|').str[0])

    rows = {}
    for suffix, tag in (('_v2', 'v2'), ('', 'v1'), ('_em', 'em')):
        g = pd.concat([agreed(rep, suffix) for rep in (1, 2, 3)])
        rows[f'agreed_{tag}'] = g.groupby('area').size()
        rows[f'in_area_{tag}'] = g[g.label == 'in_area'].groupby('area').size()
    out = pd.DataFrame(rows).fillna(0).astype(int)
    for tag in ('v2', 'v1', 'em'):
        out[f'precision_{tag}'] = (out[f'in_area_{tag}'] / out[f'agreed_{tag}'].where(out[f'agreed_{tag}'] > 0)).round(4)
    out['round_used'] = [ROUND_FOR_AREA.get(a, 'v2') for a in out.index]
    out['precision'] = [out.loc[a, f'precision_{r}'] for a, r in zip(out.index, out['round_used'])]
    out['shown'] = out['precision'] >= MIN_AREA_PRECISION
    out.index.name = 'area'
    out.to_csv(L.PROCESSED_DIR / 'domain_precision_2025.csv')
    print(out.to_string())


def pooled():
    pooled_cellpose()
    pooled_validation()
    area_precision()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = {
        'batches': (batches, 'Write second-round prompt batches.'),
        'collect': (collect, 'Collect second-round responses into label CSVs.'),
        'score': (score, 'Report agreement metrics for each second-round check.'),
        'pooled': (pooled, 'Rebuild pooled Cellpose, validation and area outputs.'),
    }
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name, (handler, help_text) in commands.items():
        subparsers.add_parser(name, help=help_text).set_defaults(handler=handler)
    args = parser.parse_args()
    args.handler()


if __name__ == '__main__':
    main()
