"""Figure 3: papers that name a package without citing it, and the reverse.

For the open-source packages whose own papers Europe PMC indexes, a paper cites
the package when Europe PMC links it to one of those papers (config/
package_papers.yml; build_citations, method 'links'). Counts are as indexed,
with no correction (Methods give the checks of index misses).
(a) Papers in 2021-2025 that name the package or cite its papers, split into
    named and not cited, named and cited, and cited and not named; rows ordered
    by the named, not cited share.
(b) Change in the named, not cited share from 2020, or the first later year with
enough naming papers, to 2025; rows aligned with panel a.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import style as fs

YEARS = (2021, 2025)
MIN_NAMED = 20   # yearly points from fewer naming papers are left out of panel b
NAMED_ONLY, BOTH, CITED_ONLY = '#D55E00', '#B8C0CA', '#0072B2'


def _yearly() -> pd.DataFrame:
    y = fs.load('mentions_citations_yearly.csv')
    return y[y.method == 'links']


def table() -> pd.DataFrame:
    """2021-2025 counts per package: mentioned, cited, both (citation links only)."""
    y = _yearly()
    t = y[y.year.between(*YEARS)].groupby('tool_id')[['named', 'cited', 'both']].sum()
    tools = fs.load('tools.csv').set_index('tool_id')
    t['label'] = [fs.tool_label(tools.loc[i, 'name']) for i in t.index]
    return t


def union(tab) -> pd.DataFrame:
    """Papers that name or cite each package, 2021-2025:
    no = named, not cited; both = named and cited; co = cited, not named."""
    out = tab[['label']].copy()
    out['no'] = tab.named - tab.both
    out['both'] = tab.both
    out['co'] = tab.cited - tab.both
    out['total'] = out.no + out.both + out.co
    for k in ('no', 'both', 'co'):
        out[f'{k}_pct'] = 100 * out[k] / out.total
    return out


def yearly() -> pd.DataFrame:
    """Named, not cited share of the papers naming or citing a package, by year,
    from the year after its first own paper; years with fewer than MIN_NAMED
    naming papers are dropped."""
    from census.build.build_citations import first_paper_year
    first = first_paper_year()
    y = _yearly()
    y = y[y.named >= MIN_NAMED].copy()
    y = y[y.year > y.tool_id.map(first)]
    y['share'] = 100 * y.named_not_cited / (y.named + y.cited_not_named)
    return y

def change(start: int = 2020, end: int = 2025) -> pd.DataFrame:
    """Named, not cited share in the first eligible year from `start` and in `end`, per package."""
    rows = []
    for tid, d in yearly().groupby('tool_id'):
        d = d.set_index('year').share
        first = [yr for yr in d.index if start <= yr < end]
        if end in d.index and first:
            rows.append(dict(tool_id=tid, start_year=first[0], start=d[first[0]], end=d[end]))
    return pd.DataFrame(rows).set_index('tool_id')


def build_figure():
    fs.set_style()
    u = union(table()).sort_values('no_pct', ascending=False)  # rows ordered by the named, not cited share
    fig = plt.figure(figsize=(7.1, 4.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.45, 1], wspace=0.42, left=0.2, right=0.9, top=0.86, bottom=0.12)
    ax = fig.add_subplot(gs[0])
    rows = np.arange(len(u))[::-1]
    left = np.zeros(len(u))
    for key, colour, label in (('no', NAMED_ONLY, 'Mentioned, not cited'), ('both', BOTH, 'Mentioned and cited'),
                               ('co', CITED_ONLY, 'Cited, not mentioned')):
        width = u[f'{key}_pct'].to_numpy()
        ax.barh(rows, width, left=left, color=colour, height=0.72, label=label)
        for yi, l0, w in zip(rows, left, width):
            if w >= 7:
                ax.text(l0 + w / 2, yi, f'{w:.0f}', fontsize=5.6, ha='center', va='center',
                        color=fs.INK if key == 'both' else 'white')
        left = left + width
    ax.set_yticks(rows, [f'{l}  ({int(v):,})' for l, v in zip(u.label, u.total)], fontsize=6.4)
    ax.set_xlim(0, 100)
    ax.set_xlabel('Papers that mention or cite the package, 2021-2025 (%)', fontsize=6.6)
    ax.tick_params(axis='y', length=0)
    ax.tick_params(axis='x', labelsize=6.2)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.0), ncol=3, fontsize=6.4, frameon=False,
              handlelength=1.2, columnspacing=1.0, borderaxespad=0.2)
    fs.panel_label(ax, 'a', x=-0.33, y=1.1)
    # (b) change in the named, not cited share, 2020 (or first eligible year) to 2025, rows as in panel a
    ch = change()
    bx = fig.add_subplot(gs[1], sharey=ax)
    for yi, tid in zip(rows, u.index):
        if tid not in ch.index:
            bx.text(2, yi, 'too few mentioning papers', fontsize=5.8, color=fs.SUB if hasattr(fs, 'SUB') else '#5F6B7A',
                    va='center', style='italic')
            continue
        a, b, y0 = ch.loc[tid, 'start'], ch.loc[tid, 'end'], int(ch.loc[tid, 'start_year'])
        bx.annotate('', xy=(b, yi), xytext=(a, yi), arrowprops=dict(arrowstyle='-|>', color=NAMED_ONLY, lw=1.4,
                    mutation_scale=7, shrinkA=2, shrinkB=0))
        bx.plot([a], [yi], 'o', ms=3.6, mfc='white', mec=NAMED_ONLY, mew=1.1, zorder=3)
        note = f"{a:.0f} → {b:.0f}" + (f" (from {y0})" if y0 != 2020 else "")
        bx.text(max(a, b) + 3, yi, note, fontsize=5.8, va='center', color=fs.INK)
    bx.set_xlim(0, 100)
    bx.set_xlabel('Mentioned, not cited (%): 2020 (circle) to 2025 (arrow)', fontsize=6.6)
    bx.tick_params(axis='y', left=False, labelleft=False)
    bx.tick_params(axis='x', labelsize=6.2)
    for side in ('top', 'right', 'left'):
        bx.spines[side].set_visible(False)
    bx.grid(axis='x', color=fs.GRID, lw=0.5)
    bx.set_axisbelow(True)
    fs.panel_label(bx, 'b', x=-0.25, y=1.1)
    return fig

def main(out_dir=None) -> None:
    fs.save(build_figure(), 'Figure3__citations', out_dir=out_dir)


if __name__ == '__main__':
    main()
