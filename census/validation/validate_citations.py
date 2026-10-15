"""Checks behind the mentions-against-citations comparison (build_citations).

papers         list each package's own papers: indexed records whose title
               names the package and whose authors include a core developer.
named YEAR     draw three disjoint seeded samples of 10 papers (census thirds
               below 30) from YEAR's papers that name a package but match none
               of its REF terms, and search each paper's parsed reference list
               (Europe PMC references service) for a work named after the
               package, by PubMed ID of its own papers or by title. A hit means
               the REF index missed a citation.
cited YEAR     draw the same design from papers whose reference list names the
               package but whose indexed text does not, and read each paper's
               full-text XML for the package's aliases (an index miss), and its
               reference list for whether the cited work is one of the
               package's own papers.

Outputs hold identifiers and flags only: data/validation/citations_*.csv.
"""
from __future__ import annotations

import argparse
import json
import re
import time

import pandas as pd

from census._http import _SESSION, _cache_path, get_json
from census._paths import DATA_DIR
from census._registry import alias_clause, build_boolean_query, load_registry
from census.build.build_citations import REF_TERMS, ref_clause
from census.sources.europepmc import API, SOURCE, _fetch_records, _id_list
from census.validation.replicates import draw_replicates

N = 10
SEED = '20261013-citations-v1'
REST = 'https://www.ebi.ac.uk/europepmc/webservices/rest'
VAL = DATA_DIR / 'validation'
REF_LIST = re.compile(r'<ref-list\b.*?</ref-list>', re.S)
# Core developers (Europe PMC AUTH form); a package's own papers name it in the title and list one of them.
DEVELOPERS = {
    'imagej': ['Schindelin J', 'Rueden CT', 'Eliceiri KW', 'Rasband WS', 'Schneider CA', 'Arganda-Carreras I', 'Tomancak P', 'Cardona A'],
    'qupath': ['Bankhead P'],
    'cellprofiler': ['Carpenter AE', 'Cimini BA', 'Kamentsky L', 'Jones TR', 'Lamprecht MR', 'McQuin C', 'Stirling DR'],
    'ilastik': ['Hamprecht FA', 'Kreshuk A', 'Sommer C', 'Berg S'],
    'napari': ['Sofroniew N', 'Lambert T', 'Evans K', 'Nunez-Iglesias J'],
    'icy': ['Olivo-Marin JC', 'de Chaumont F'],
    'knime': ['Berthold MR', 'Dietz C'],
    'cellpose': ['Stringer C', 'Pachitariu M'],
    'stardist': ['Weigert M', 'Schmidt U'],
    'deepimagej': ['Gomez-de-Mariscal E', 'Sage D', 'Munoz-Barrutia A', 'Garcia-Lopez-de-Haro C'],
    'zerocostdl4mic': ['von Chamier L', 'Jacquemet G', 'Henriques R', 'Hidalgo-Cenalmor I', 'Gomez-de-Mariscal E'],
    'jupyter': ['Kluyver T', 'Perez F', 'Granger BE'],
    'skimage': ['van der Walt S', 'Nunez-Iglesias J'],
    'opencv': ['Bradski G'],
}


def own_papers(tool_id):
    """(id, source, year) of each indexed record titled with the package and authored by a core developer."""
    title = ' OR '.join(f'TITLE:"{t}"' for t in REF_TERMS[tool_id])
    auth = ' OR '.join(f'AUTH:"{a}"' for a in DEVELOPERS[tool_id])
    data = get_json(SOURCE, API, {'query': f'({title}) AND ({auth})', 'format': 'json', 'resultType': 'lite', 'pageSize': 1000})
    return [(r['id'], r['source'], r.get('pubYear'), r.get('title', '')) for r in (data.get('resultList') or {}).get('result', [])]


def references(pid, src):
    try:
        data = get_json(SOURCE, f'{REST}/{src}/{pid}/references', {'page': 1, 'pageSize': 1000, 'format': 'json'}, max_retries=3)
    except RuntimeError:  # a record the service keeps failing on counts as having no parsed references
        return []
    return (data.get('referenceList') or {}).get('reference', [])


def named_ref(refs, own_ids, terms):
    """'own' if a reference is one of the package's papers, 'other' if only another work named after it, else None."""
    low = [t.lower() for t in terms]
    if any(r.get('id') in own_ids for r in refs):
        return 'own'
    if any(any(t in (r.get('title') or '').lower() for t in low) for r in refs):
        return 'other'
    return None


def full_text(pmcid):
    """Full-text XML of an open-access record, cached like the JSON responses; None when absent."""
    if not pmcid:
        return None
    url = f'{REST}/{pmcid}/fullTextXML'
    cache = _cache_path(SOURCE, url, {'accept': 'xml'})
    if not cache.exists():
        for attempt in range(4):
            resp = _SESSION.get(url, timeout=60, headers={'Accept': 'application/xml'})  # the session default (JSON) gets 406
            if resp.status_code < 500:
                break
            time.sleep(2 ** (attempt + 1))
        else:
            return None  # server error persisted; not cached, so a later run retries
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
        cache.write_text(json.dumps(resp.text if resp.ok else ''))
    return json.loads(cache.read_text()) or None


def frame(tool, reg, year, kind):
    named = build_boolean_query(tool, reg.context_query, wildcard=True)
    ref = ref_clause(REF_TERMS[tool.id])
    if kind == 'named':
        q = f'{named} AND PUB_YEAR:{year} NOT {ref}'
    else:
        q = f'{ref} AND ({reg.context_query}) AND PUB_YEAR:{year} NOT {alias_clause(tool, wildcard=True)}'
    return sorted(set(_id_list(q)))  # cursor paging can repeat a record


def run(kind, year):
    reg = load_registry()
    rows = []
    for tool in reg.tools:
        if tool.id not in REF_TERMS:
            continue
        own_ids = {p[0] for p in own_papers(tool.id) if p[1] == 'MED'}
        units = frame(tool, reg, year, kind)
        parts = draw_replicates(units, N, seed=f'{SEED}-{kind}-{year}-{tool.id}')
        pmc = {}
        if kind == 'cited':
            recs = _fetch_records([u for part in parts for u in part])
            pmc = {(r.get('id'), r.get('source')): r.get('pmcid') for r in recs}
        alias_re = re.compile('|'.join(re.escape(a) for a in tool.aliases), re.I)
        print(f'{tool.id}: start', flush=True)
        for rep, part in enumerate(parts, start=1):
            for pid, src in part:
                refs = references(pid, src)
                row = dict(tool_id=tool.id, year=year, replicate=rep, epmc_id=pid, source=src, frame=len(units),
                           n_refs=len(refs), cited_work=named_ref(refs, own_ids, REF_TERMS[tool.id]) if refs else None)
                if kind == 'cited':
                    xml = full_text(pmc.get((pid, src)))
                    row['full_text'] = xml is not None
                    # search the article without its reference list, whose cited titles carry the name
                    text = REF_LIST.sub(' ', xml) if xml else None
                    row['name_in_full_text'] = bool(alias_re.search(text)) if text else None
                rows.append(row)
        print(f'{tool.id}: frame {len(units)}, own papers {len(own_ids)}, sampled {sum(map(len, parts))}', flush=True)
    out = pd.DataFrame(rows)
    path = VAL / f'citations_{kind}_not_{"cited" if kind == "named" else "named"}_{year}.csv'
    out.to_csv(path, index=False)
    print(f'wrote {path}')
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['papers', 'named', 'cited'])
    ap.add_argument('year', nargs='?', type=int, default=2025)
    a = ap.parse_args()
    if a.step == 'papers':
        rows = [dict(tool_id=t, epmc_id=i, source=s, year=y, title=ti) for t in REF_TERMS for i, s, y, ti in own_papers(t)]
        out = pd.DataFrame(rows)
        # titles are article text: keep them in gitignored data/raw/, publish identifiers only
        raw = DATA_DIR / 'raw' / 'citations'
        raw.mkdir(parents=True, exist_ok=True)
        out.to_csv(raw / 'citations_package_papers_titles.csv', index=False)
        out.drop(columns='title').to_csv(VAL / 'citations_package_papers.csv', index=False)
        print(out.groupby('tool_id').size().to_string())
        return
    out = run(a.step, a.year)
    if a.step == 'named':
        p = out[out.n_refs > 0]
        s = p.groupby('tool_id').agg(parsed=('epmc_id', 'size'), missed=('cited_work', lambda x: int(x.notna().sum())))
    else:
        p = out[out.full_text == True]  # noqa: E712
        s = p.groupby('tool_id').agg(full_text=('epmc_id', 'size'), name_in_text=('name_in_full_text', 'sum'),
                                     own_paper=('cited_work', lambda x: int((x == 'own').sum())))
    print(s.to_string())


if __name__ == '__main__':
    main()
