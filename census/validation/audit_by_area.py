"""Split the pooled reporting audit by Figure 5 computational-methods vocabulary.

Run offline from the pipeline root: python -m census.validation.audit_by_area.
Shares describe unweighted audited package-paper records, not population rates.
Unavailable title/abstract text stays in pooled totals and is reported separately;
it receives no vocabulary flag and contributes to neither vocabulary stratum.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import pandas as pd

from census._paths import PROCESSED_DIR, RAW_DIR
from census.figures.domains import DOMAINS

PATTERN = re.compile(DOMAINS['Computational methods'], re.I)


def load_records(audit_dir: Path = RAW_DIR / 'replicates' / 'audit',
                 xml_dir: Path = RAW_DIR / 'europepmc_fulltext') -> pd.DataFrame:
    """Read all receipts, applying the published scope and name-only definitions."""
    @lru_cache(maxsize=None)
    def vocabulary(pmcid):
        try:
            root = ET.parse(xml_dir / f'{pmcid}.xml').getroot()
        except (OSError, ET.ParseError):
            return pd.NA
        for e in root.iter():
            e.tag = e.tag.split('}')[-1]
        # Only this article's metadata: reference titles and body text do not count.
        nodes = root.findall('./front/article-meta/title-group/article-title')
        nodes += root.findall('./front/article-meta/abstract')
        text = ' '.join(t.strip() for e in nodes for t in e.itertext() if t.strip())
        return bool(PATTERN.search(text)) if text else pd.NA

    rows = []
    for path in sorted(audit_dir.glob('*.json')):
        obj = json.loads(path.read_text())
        for receipt in obj['receipts']:
            for r in receipt['rows']:
                analysed = r['scope'] != 'none'
                flag = vocabulary(r['pmcid'])
                rows.append(dict(tool_id=obj['tool_id'], pmcid=r['pmcid'],
                                 replicate=receipt['replicate'],
                                 analysed=analysed,
                                 name_only=not (r['version'] or r['function'] or r['parameter']) if analysed else pd.NA,
                                 methods_vocabulary=flag, missing_text=pd.isna(flag)))
    if not rows:
        raise ValueError(f'No audit records in {audit_dir}')
    return pd.DataFrame(rows)


def summarise(d: pd.DataFrame) -> pd.DataFrame:
    """Package counts and percentages, with unknown vocabulary kept separate."""
    rows = []
    for tool, sampled in d.groupby('tool_id', sort=True):
        g = sampled[sampled.analysed] if 'analysed' in sampled else sampled
        known = g[g.methods_vocabulary.notna()]
        with_vocab = known[known.methods_vocabulary == True]
        rec = dict(tool_id=tool, n=len(g), name_only_n=int(g.name_only.sum()),
                   name_only_pct=100 * g.name_only.mean(),
                   sampled_n=len(sampled), excluded_n=len(sampled) - len(g),
                   missing_text_n=int(sampled.missing_text.sum()),
                   vocabulary_n=len(with_vocab), vocabulary_text_n=len(known),
                   vocabulary_pct=100 * len(with_vocab) / len(known) if len(known) else float('nan'))
        for label, flag in [('without', False), ('with', True)]:
            sub = known[known.methods_vocabulary == flag]
            rec.update({f'{label}_vocabulary_n': len(sub),
                        f'{label}_vocabulary_name_only_n': int(sub.name_only.sum()),
                        f'{label}_vocabulary_name_only_pct': 100 * sub.name_only.mean()})
        rows.append(rec)
    return pd.DataFrame(rows)


def gaps(d: pd.DataFrame) -> pd.DataFrame:
    """ImageJ/Fiji minus other packages: raw and Mantel-Haenszel risk differences.

    Each stratum has weight n_ImageJ * n_other / (n_ImageJ + n_other).
    This directly averages risk differences; it does not transform an odds ratio.
    Repeated papers across packages remain separate package-paper records.
    """
    if 'analysed' in d:
        d = d[d.analysed]
    imagej = d.tool_id == 'imagej'
    raw = d.loc[imagej, 'name_only'].mean() - d.loc[~imagej, 'name_only'].mean()
    numerator = denominator = 0.0
    for flag in (False, True):
        sub = d[d.methods_vocabulary == flag]
        a = sub.loc[sub.tool_id == 'imagej', 'name_only']
        b = sub.loc[sub.tool_id != 'imagej', 'name_only']
        if len(a) and len(b):
            weight = len(a) * len(b) / (len(a) + len(b))
            numerator += weight * (a.mean() - b.mean())
            denominator += weight
    return pd.DataFrame([dict(raw_gap_pp=100 * raw,
                              stratified_gap_pp=100 * numerator / denominator if denominator else float('nan'),
                              n=len(d), stratified_n=int(d.methods_vocabulary.notna().sum()))])


def main() -> None:
    d = load_records()
    summary = summarise(d)
    # Refuse to publish an area split that does not reproduce the pooled audit.
    published = pd.read_csv(PROCESSED_DIR / 'reporting_audit_pooled_2025.csv').set_index('tool_id')
    got = summary.set_index('tool_id')
    if set(got.index) != set(published.index):
        raise ValueError('Package set differs from published audit')
    for tool, row in published.iterrows():
        if (got.loc[tool, 'n'] != row.analysed or
                got.loc[tool, 'name_only_n'] != row.name_only_n or
                abs(got.loc[tool, 'name_only_pct'] - row.name_only_pct) > 1e-9):
            raise ValueError(f'Pooled audit mismatch: {tool}')
    summary.to_csv(PROCESSED_DIR / 'reporting_audit_by_area_2025.csv', index=False)
    gaps(d).to_csv(PROCESSED_DIR / 'reporting_audit_area_gap_2025.csv', index=False)
    missing = d[d.missing_text][['tool_id', 'pmcid', 'replicate', 'analysed']]
    missing.to_csv(PROCESSED_DIR / 'reporting_audit_area_missing_text_2025.csv', index=False)
    print(summary.to_string(index=False))
    print(gaps(d).to_string(index=False))
    print(f'Unavailable XML/title/abstract text: {len(missing)} records (see missing-text CSV)')


if __name__ == '__main__':
    main()
