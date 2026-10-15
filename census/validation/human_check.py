"""Human check of the Cellpose workflow labels, replicate 1 (2025).

One author read the full text of the 40 replicate-1 papers, including linked
repositories and cited protocols where the text pointed to them, and labelled
them with the first-round rubric (cellpose_workflow_2025_human_r1.csv). The
three 'separate_*' labels merge into the second-round 'separate' category so
the human labels compare with the two model annotators' second-round labels.

Writes data/processed/cellpose_human_check_2025.csv (metric, value).
Run: python -m census.validation.human_check
"""
from __future__ import annotations

import pandas as pd

from census._paths import PROCESSED_DIR
from census.validation import label_replicates as L

MERGE = {'separate_fiji_measure': 'separate', 'separate_fiji_other': 'separate', 'separate_elsewhere': 'separate'}
CATS = ['separate', 'inside_fiji', 'other_pipeline', 'unclear', 'mention_only']


def main() -> None:
    h = pd.read_csv(L.VAL / 'cellpose_workflow_2025_human_r1.csv', comment='#', dtype=str)
    h = h.assign(pmcid=h.pmcid.str.strip(), human=h.label.str.strip().replace(MERGE)).set_index('pmcid').human
    items = pd.read_csv(L.VAL / 'cellpose_workflow_2025_items_r1.csv', dtype=str).pmcid
    assert set(h.index) == set(items), 'human labels must cover replicate 1 exactly'
    model = {}
    for ann in ('deepseek', 'glm'):
        d = pd.read_csv(L.VAL / f'cellpose_workflow_2025_labels_{ann}_r1_v2.csv', dtype=str)
        model[ann] = d.set_index(d.item_id.str.split('|').str[-1]).workflow.reindex(h.index)
    cons = model['deepseek'].where(model['deepseek'] == model['glm']).dropna()
    rows = {'papers': len(h),
            'agree_deepseek': int((h == model['deepseek']).sum()),
            'agree_glm': int((h == model['glm']).sum()),
            'consensus_papers': len(cons),
            'agree_consensus': int((h.loc[cons.index] == cons).sum())}
    rows.update({f'human_{c}': int((h == c).sum()) for c in CATS})
    rows.update({f'consensus_{c}': int((cons == c).sum()) for c in CATS})
    out = pd.Series(rows, name='value').rename_axis('metric')
    out.to_csv(PROCESSED_DIR / 'cellpose_human_check_2025.csv')
    print(out.to_string())


if __name__ == '__main__':
    main()
