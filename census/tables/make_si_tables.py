"""Fill the Supplementary Information tables from processed CSVs.

The reporting-audit and validation tables read pooled inputs. After collecting
and committing the labels, run `python -m census.run_all --pool`.

In the manuscript checkout each table sits between named markers in
MANUSCRIPT/02_SUPPLEMENTARY_INFO.md and is rewritten there. Standalone, all
tables go to tables/output/supplementary_tables.md.

Run from the pipeline root:
    python -m census.tables.make_si_tables
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import yaml

from census._paths import PROCESSED_DIR, REPO_ROOT, SCRIPTS_DIR, TOOLS_YML  # noqa: E402

SI = REPO_ROOT / "MANUSCRIPT" / "02_SUPPLEMENTARY_INFO.md"
OUTPUT = SCRIPTS_DIR / "tables" / "output" / "supplementary_tables.md"
YEARS = [2010, 2015, 2019, 2025]
CATEGORY = {"general-platform": "open platform", "dl-model": "deep-learning method",
            "notebook": "notebook", "commercial": "commercial package",
            "library": "Python library", "acquisition-suite": "microscope control",
            "figure-preparation": "image-editing / figure-preparation software"}
VALIDATION = PROCESSED_DIR.parent / "validation"



def _pct(v: float) -> str:
    """Whole-number percentage; values under 0.5 print as <1 (no decimals in the manuscript)."""
    return "<1" if 0 < v < 0.5 else str(int(v + 0.5))

def _md(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |"
    rule = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, rule, *rows])


def _n(v) -> str:
    return f"{int(v):,}" if pd.notna(v) else ""


# Notes the registry table carries beside package aliases.
ALIAS_NOTE = {"zerocostdl4mic": " (every paper mentioning DL4MicEverywhere also matches these)"}


def registry() -> str:
    raw = yaml.safe_load(TOOLS_YML.read_text())
    aggregate = [t for t in raw["tools"] if t.get("in_aggregate", True)]
    aggregate_total = len(aggregate)
    rows = [{"Package": t["name"].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
             "Category": CATEGORY.get(t["category"], t["category"]),
             "Query aliases (OR)": "; ".join(f"\"{a}\"" for a in t["aliases"]) + ALIAS_NOTE.get(t["id"], ""),
             "Counted in": ("neither" if t.get("in_aggregate", True) is False
                            else f"{aggregate_total}-package total" if t["category"] == "acquisition-suite"
                            else "both totals"),
             "Caveat": t.get("caveat", "")}
            for t in raw["tools"]]
    return _md(pd.DataFrame(rows))


def literature() -> str:
    lit = pd.read_csv(PROCESSED_DIR / "literature_yearly.csv")
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    corpus = pd.read_csv(PROCESSED_DIR / "corpus_yearly.csv").set_index("year")["microscopy_papers"]
    lit = lit[lit["tool_id"] != "nihimage"]
    ep = lit[lit["source"] == "europepmc"].pivot(index="tool_id", columns="year", values="count")
    oa = lit[lit["source"] == "openalex"].groupby("tool_id")["count"].sum()
    ep = ep.sort_values(2025, ascending=False)
    rows = []
    for t, r in ep.iterrows():
        row = {"Package": names[t].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME")}
        for y in YEARS:
            row[str(y)] = _n(r[y])
        row["% of microscopy papers, 2025"] = _pct(100 * r[2025] / corpus[2025])
        row["Europe PMC, 2010-2025"] = _n(r.sum())
        row["OpenAlex, 2010-2025"] = _n(oa.get(t))
        rows.append(row)
    rows.append({"Package": "All microscopy papers", **{str(y): _n(corpus[y]) for y in YEARS},
                 "% of microscopy papers, 2025": "100", "Europe PMC, 2010-2025": _n(corpus.sum()),
                 "OpenAlex, 2010-2025": ""})
    return _md(pd.DataFrame(rows))


# GitHub counts come from the repositories listed in tools.yml; say so where a package has several names.
REPO_NOTE = {"zerocostdl4mic": " (ZeroCostDL4Mic repository)"}


def adoption() -> str:
    snap = pd.read_csv(PROCESSED_DIR / "adoption_snapshot.csv")
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    rows = []
    for r in snap.itertuples(index=False):
        rows.append({"Package": names[r.tool_id].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME") + REPO_NOTE.get(r.tool_id, ""),
                     "GitHub stars": _n(r.github_stars) if str(r.github_stars) != "nan" else "",
                     "GitHub forks": _n(r.github_forks) if str(r.github_forks) != "nan" else "",
                     "Earliest repository": r.earliest_repo if isinstance(r.earliest_repo, str) else "",
                     "PyPI downloads, 30 days": _n(r.pypi_downloads_30d)
                     if str(r.pypi_downloads_30d) not in ("nan", "") else "no package"})
    return _md(pd.DataFrame(rows))


def deep_learning() -> str:
    est = pd.read_csv(PROCESSED_DIR / "dl_estimates.csv")
    if "population" not in est.columns:
        return _md(pd.DataFrame([{"Status": "pending", "Detail": "random-sample re-run not yet complete"}]))
    sp = pd.read_csv(PROCESSED_DIR / "dl_split_yearly.csv")
    sp25 = sp[sp["year"] == 2025].set_index("tool_id")["base_count"]
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    est = est[est["year"] == 2025].sort_values("dl_fraction", ascending=False)
    rows = []
    for r in est.itertuples(index=False):
        pop = sp25.get(r.tool_id, r.population)
        # Census is judged against the sampler's own id-list population; the
        # hit count in literature_yearly can differ by a record or two.
        is_census = r.n_sampled >= r.population
        ci_str = (f"{_pct(100 * r.dl_fraction)}% (census)" if is_census
                  else f"{_pct(100 * r.dl_fraction)}% ({_pct(100 * r.ci_lo)}-{_pct(100 * r.ci_hi)})")
        rows.append({
            "Package": names[r.tool_id].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
            "Matches, 2025": _n(pop),
            "Sampled": _n(r.n_sampled),
            "Labelled deep learning": _n(r.n_dl),
            "Share (95% CI)": ci_str,
        })
    return _md(pd.DataFrame(rows))


def methods_section() -> str:
    m = pd.read_csv(PROCESSED_DIR / "methods_section_2025.csv")
    m = m[m["tool_id"] != "nihimage"]
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    m = m.sort_values("n_all", ascending=False)
    rows = [{"Package": names[r.tool_id].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
             "Matches, 2025": _n(r.n_all),
             "Mentioned in Methods": _n(r.n_methods),
             "Share in Methods": f"{_pct(100 * r.share_methods)}%" if pd.notna(r.share_methods) else "",
             "In references, not in Methods": _n(r.n_refs_not_methods)}
            for r in m.itertuples(index=False)]
    return _md(pd.DataFrame(rows))


def reporting() -> str:
    r = pd.read_csv(PROCESSED_DIR / "reporting_audit_pooled_2025.csv")

    def ci(row, ind):
        # packages read in full (all but a few unavailable papers) carry no sampling interval
        if row["analysed"] >= row["frame"] - 5:
            return _pct(row[ind + "_pct"])
        return f"{_pct(row[ind + '_pct'])} ({_pct(row[ind + '_lo'])}-{_pct(row[ind + '_hi'])})"

    rows = [{"Package": row["name"].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
             "Papers in frame": _n(row["frame"]),
             "Papers analysed": _n(row["analysed"]),
             "Version, %": ci(row, "version"),
             "Named function, %": ci(row, "function"),
             "Parameter, %": ci(row, "parameter"),
             "Version and function or parameter, %": ci(row, "complete"),
             "Name only, %": _pct(row["name_only_pct"]),
             "Code shared, %": ci(row, "code")}
            for _, row in r.iterrows()]
    return _md(pd.DataFrame(rows))


def mesh() -> str:
    """Keyword-positive papers with MeSH and sampling-adjusted agreement."""
    data = pd.read_csv(PROCESSED_DIR / 'mesh_check_2021_2025.csv')
    rows = [{'Area': r.area,
             'Papers with MeSH, n': _n(r.n_keyword_with_mesh),
             'Agreement with MeSH, % (95% CI)':
                 f'{_pct(100 * r.agreement_any)} '
                 f'({_pct(100 * r.agreement_any_wilson_lo)}-{_pct(100 * r.agreement_any_wilson_hi)})',
             "Cohen's kappa": f'{r.kappa_any:.2f}'}
            for r in data.itertuples(index=False)]
    return _md(pd.DataFrame(rows))


def audit_area() -> str:
    """Reporting-audit shares split by title/abstract methods vocabulary."""
    area = pd.read_csv(PROCESSED_DIR / 'reporting_audit_by_area_2025.csv').set_index('tool_id')
    published = pd.read_csv(PROCESSED_DIR / 'reporting_audit_pooled_2025.csv')
    rows = []
    for p in published.itertuples(index=False):
        r = area.loc[p.tool_id]
        def cell(label):
            return (f"{_pct(r[label + '_vocabulary_name_only_pct'])} "
                    f"({_n(r[label + '_vocabulary_name_only_n'])}/{_n(r[label + '_vocabulary_n'])})")
        rows.append({'Package': p.name.replace(' / ', '/'),
                     'Papers with methods vocabulary, %': _pct(r.vocabulary_pct),
                     'Name only without vocabulary, % (n)': cell('without'),
                     'Name only with vocabulary, % (n)': cell('with')})
    return _md(pd.DataFrame(rows))


def validation() -> str:
    """Validation checks: three disjoint samples each, labels on which two annotators agreed."""
    v = pd.read_csv(PROCESSED_DIR / "validation_pooled_2025.csv").set_index("metric")
    def per(num, den):
        vals = [100 * v.loc[num, r] / v.loc[den, r] for r in ("r1", "r2", "r3")]
        return f"{_pct(min(vals))}-{_pct(max(vals))}%"

    rows = [
        {"Check": "Aliases, 15 added packages",
         "Sample": "3 x 150",
         "Result": f"{v.loc['alias_software', 'pooled']} of {v.loc['alias_agreed', 'pooled']} mention the software ({per('alias_software', 'alias_agreed')})"},
        {"Check": "Aliases, 15 core packages",
         "Sample": "3 x {}-{}".format(*sorted(v.loc['alias_core_labelled', ['r1', 'r2', 'r3']])[::2]),
         "Result": f"{v.loc['alias_core_software', 'pooled']} of {v.loc['alias_core_agreed', 'pooled']} mention the software ({per('alias_core_software', 'alias_core_agreed')})"},
        {"Check": "Microscope-control use, same matches",
         "Sample": f"{v.loc['acq_agreed', 'pooled']} agreed",
         "Result": f"acquisition {v.loc['acq_acquisition', 'pooled']}, analysis {v.loc['acq_analysis', 'pooled']}, unclear {v.loc['acq_unclear', 'pooled']}"},
        {"Check": "Lexicon-positive abstracts",
         "Sample": "3 x 80",
         "Result": f"{v.loc['lex_pos_dl', 'pooled']} of {v.loc['lex_pos_agreed', 'pooled']} deep learning ({per('lex_pos_dl', 'lex_pos_agreed')})"},
        {"Check": "Lexicon-negative abstracts",
         "Sample": "3 x 120",
         "Result": f"{v.loc['lex_neg_dl', 'pooled']} of {v.loc['lex_neg_agreed', 'pooled']} deep learning ({', '.join(str(v.loc['lex_neg_dl', r]) for r in ('r1', 'r2', 'r3'))})"},
        {"Check": "Research-area keywords",
         "Sample": "3 x 112",
         "Result": f"{v.loc['dom_in_area', 'pooled']} of {v.loc['dom_agreed', 'pooled']} in the area ({per('dom_in_area', 'dom_agreed')})"},
    ]
    for label, f in (("Cellpose", "cellpose_workflow_pooled_2025.csv"), ("StarDist", "stardist_workflow_2025_pooled.csv"),
                     ("ilastik", "ilastik_workflow_2025_pooled.csv")):
        c = pd.read_csv(PROCESSED_DIR / f).set_index("category")
        rows.append({"Check": f"{label} workflow", "Sample": "3 x 40",
                     "Result": (f"{c.loc['agreed', 'pooled']} agreed: {c.loc['separate', 'pooled']} own, {c.loc['inside_fiji', 'pooled']} in Fiji, "
                                f"{c.loc['other_pipeline', 'pooled']} other, {c.loc['unclear', 'pooled']} not stated, "
                                f"{c.loc['mention_only', 'pooled']} unused")})
    return _md(pd.DataFrame(rows))



def methods_micro() -> str:
    m = pd.read_csv(PROCESSED_DIR / "methods_microscopy_yearly.csv")
    tools = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")
    keep = tools.index[(tools["in_aggregate"].astype(str).str.lower() == "true")]
    p = m.pivot(index="tool_id", columns="year", values="count").loc[lambda d: d.index.isin(keep)]
    corpus = m.groupby("year")["methods_microscopy_papers"].first()
    p = p.sort_values(2025, ascending=False)
    rows = [{"Package": tools.loc[t, "name"].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"), "2010": _n(r[2010]), "2025": _n(r[2025]),
             "% of papers, 2025": _pct(100 * r[2025] / corpus[2025])} for t, r in p.iterrows()]
    rows.append({"Package": "Papers whose Methods mention microscopy", "2010": _n(corpus[2010]),
                 "2025": _n(corpus[2025]), "% of papers, 2025": "100"})
    return _md(pd.DataFrame(rows))


# Wildcard tokens that still name the same package: editions, versions and
# fused spellings. Tokens outside this set are other words, most of them
# personal names or neighbouring products (Avizohar, CellSensor).
PRODUCT_VARIANTS = frozenset({
    "AiviaCommunity", "ArivisVision4D", "AxioVisionLE", "AxioVisionRel", "AxiovisionRel",
    "CellPose3D", "CellSensDimension", "CellSensEntry", "ImageJ2x", "ImageJv1", "ImarisCell",
    "ImarisColoc", "ImarisViewer", "ImarisViewer10", "Imarisx64", "JupyterHub", "JupyterLab",
    "JupyterLab33", "JupyterLite", "JupyterNotebook", "Jupyterlab", "jupyterlab", "OpenCVv3",
    "StarDist2D", "StarDist3D", "StarDistOPP", "Stardist2D", "VolocityDemo",
    "ZeroCostDL4Microscopy", "Avizo3D",
})

# Packages whose query uses product phrases and vendor names, never the bare word.
PRODUCT_PHRASE_QUERIES = frozenset({"icy", "halo", "huygens", "dragonfly", "zen", "lasx"})

# Why a bare name can mislead: an ordinary word, a person, a place, general
# software or a similar software name. Every other registry package is distinctive.
NAME_TYPE = {"icy": "ordinary word", "halo": "ordinary word", "dragonfly": "ordinary word",
             "zen": "ordinary word", "metamorph": "ordinary word",
             "amira": "personal name", "huygens": "personal name",
             "imagej": "country or place", "matlab": "general software",
             "nihimage": "similar software name"}

SINGLE_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _wildcard_kinds() -> pd.DataFrame:
    """Per-package classification of the 2025 wildcard additions, no_full_text rows dropped.
    fused: name or number fused to the name (exact and digits); variant: letters in
    PRODUCT_VARIANTS; other: letters outside it; absent: name not found in the text."""
    a = pd.read_csv(VALIDATION / "wildcard_additions_2025.csv")
    a = a[a["kind"] != "no_full_text"]
    letters = a["kind"] == "letters"
    return pd.DataFrame({
        "tool_id": a["tool_id"],
        "fused": a["kind"].isin(["exact", "digits"]),
        "variant": letters & a["token"].isin(PRODUCT_VARIANTS),
        "other": letters & ~a["token"].isin(PRODUCT_VARIANTS),
        "absent": a["kind"] == "absent",
    }).groupby("tool_id").sum().astype(int)


def wildcard() -> str:
    """What the trailing wildcard adds to each analysis package in 2025.

    Exact and wildcard counts come from the fresh Europe PMC pull
    (build_wildcard_sensitivity); the classification comes from the three seeded
    samples of papers only the wildcard finds (validate_wildcards). Added (%) is
    the rise over the exact count, and n excludes papers without full text. The
    last row gives ImageJ/Fiji's share of the analysis packages' mentions,
    exact and wildcard, for 2010, 2020 and 2025.
    """
    s = pd.read_csv(PROCESSED_DIR / "wildcard_sensitivity.csv")
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    kinds = _wildcard_kinds()
    a = s[s["analysis"]]
    rows = []
    for r in a[a["year"] == 2025].sort_values("exact", ascending=False).itertuples(index=False):
        k = kinds.loc[r.tool_id] if r.tool_id in kinds.index else None
        rows.append({
            "Package": names[r.tool_id].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
            "2025 exact": _n(r.exact),
            "2025 wildcard": _n(r.wildcard),
            "Added (%)": f"{_pct(100 * (r.wildcard - r.exact) / r.exact)}%" if r.exact else "",
            "Added papers checked (n)": _n(k.sum()) if k is not None else "",
            "Fused name or number": _n(k["fused"]) if k is not None else "",
            "Product variant": _n(k["variant"]) if k is not None else "",
            "Other word": _n(k["other"]) if k is not None else "",
            "Not found in text": _n(k["absent"]) if k is not None else "",
        })
    ij = a[a["tool_id"] == "imagej"].set_index("year")
    share = {form: " / ".join(f"{100 * ij.loc[y, form] / a[a['year'] == y][form].sum():.1f}%"
                              for y in (2010, 2020, 2025)) for form in ("exact", "wildcard")}
    rows.append({"Package": "ImageJ/Fiji share of analysis mentions", "2025 exact": share["exact"],
                 "2025 wildcard": share["wildcard"], "Added (%)": "", "Added papers checked (n)": "",
                 "Fused name or number": "", "Product variant": "", "Other word": "",
                 "Not found in text": ""})
    return _md(pd.DataFrame(rows))


def _alias_precision() -> dict[str, tuple[int, int]]:
    """Per-package counts of software labels and total labels.

    Existing alias draws include only dual-annotator agreements; the new-package
    samples use one AI annotation per paper, checked in an independent review.
    """
    out: dict[str, tuple[int, int]] = {}
    # added packages (alias_precision_2025) and core packages (alias_precision_core_2025)
    for name, rep in ((n, r) for n in ("alias_precision_2025", "alias_precision_core_2025") for r in (1, 2, 3)):
        a = pd.read_csv(VALIDATION / "replicates" / f"{name}_labels_deepseek_r{rep}.csv",
                        dtype=str).set_index("item_id")
        b = pd.read_csv(VALIDATION / "replicates" / f"{name}_labels_glm_r{rep}.csv",
                        dtype=str).set_index("item_id")
        common = a.index.intersection(b.index)
        agreed = a.loc[common, "sense"]
        agreed = agreed[agreed == b.loc[common, "sense"]]
        for item, sense in agreed.items():
            k, n = out.get(item.split("|")[0], (0, 0))
            out[item.split("|")[0]] = (k + int(sense == "software"), n + 1)
    labels_path = VALIDATION / "registry_precision_2026.csv"
    labels = pd.read_csv(labels_path, dtype=str)
    required = {"tool_id", "year", "pmcid", "label", "use", "meaning"}
    if not required.issubset(labels.columns):
        raise ValueError(f"{labels_path.name}: missing columns {sorted(required - set(labels.columns))}")
    labels = labels.fillna("")
    if not labels["label"].isin({"software", "false_positive"}).all():
        raise ValueError(f"{labels_path.name}: labels must be software or false_positive")
    use_categories = {"figure-assembly", "image-processing-or-analysis", "illustration", "listed-only", "unclear"}
    meaning_categories = {"nih-image-program", "imagej-meant", "derivative", "unclear"}
    for tool_id, group in labels[labels.tool_id != "nihimage"].groupby("tool_id"):
        if len(group) != 40 or group["pmcid"].nunique() != 40:
            raise ValueError(f"{tool_id}: expected 40 unique full-text papers")
        out[tool_id] = (int(group["label"].eq("software").sum()), len(group))
    photoshop = labels[labels.tool_id == "photoshop"]
    if len(photoshop) != 40 or not photoshop["use"].isin(use_categories).all():
        raise ValueError("photoshop: expected a valid use label for all 40 matches")
    nih = labels[labels.tool_id == "nihimage"]
    recent = nih[nih.year.isin(["2024", "2025"])]
    historical = nih[nih.year.isin([str(y) for y in range(1995, 2004)])]
    if len(recent) != 40 or recent.pmcid.nunique() != 40:
        raise ValueError("nihimage: expected 40 unique recent full-text matches")
    if not 1 <= len(historical) <= 40 or historical.pmcid.nunique() != len(historical):
        raise ValueError("nihimage: expected up to 40 unique historical full-text matches")
    if not nih["meaning"].isin(meaning_categories).all():
        raise ValueError("nihimage: every recent and historical match needs a meaning label")
    out["nihimage"] = (int(historical["label"].eq("software").sum()), len(historical))
    return out


def queryerrors() -> str:
    """Why each package's name is hard to query and what the loss costs.

    One row per registry package, in registry order. Precision is the share of labels
    where the name refers to software; false-positive rates are reported separately.
    Image-Pro and Photoshop use 40 open-access matches from 2025. NIH Image precision
    uses the historical 1995-2003 sample; its 2024-2025 sample has separate meaning labels.
    Citation omissions come from 2021-2025 counts; their last column is the 2025
    full-text check. Packages with no world list entry hold no reference paper.
    """
    cfg = yaml.safe_load(TOOLS_YML.read_text())
    exact = frozenset(cfg["settings"]["exact_aliases"])
    aliases = {t["id"]: t["aliases"] for t in cfg["tools"]}
    packages = pd.read_csv(PROCESSED_DIR / "tools.csv")
    m = pd.read_csv(PROCESSED_DIR / "mentions_citations_yearly.csv")
    m = m[m["year"].between(2021, 2025)].groupby("tool_id")[["cited", "cited_not_named"]].sum()
    c = pd.read_csv(VALIDATION / "citations_cited_not_named_2025.csv")
    c = c[c["full_text"].eq(True)]
    found = c.groupby("tool_id")["name_in_full_text"].agg(k=lambda x: int(x.eq(True).sum()), n="size")
    kinds = _wildcard_kinds()
    prec = _alias_precision()
    rows = []
    for t in packages["tool_id"]:
        if t in PRODUCT_PHRASE_QUERIES:
            query = "product phrases"
        elif any(SINGLE_WORD.fullmatch(a) and a not in exact for a in aliases[t]):
            query = "name (wildcard in citation analysis)"  # the census is exact; Figure 3 and the wildcard table add a trailing *
        else:
            query = "name"
        k, n = prec.get(t, (0, 0))
        cell = "not sampled" if n == 0 else f"{_pct(100 * k / n)}% ({k}/{n})" if n >= 5 else f"{k}/{n}"
        false_positive = ("not sampled" if n == 0 else
                          f"{100 * (n - k) / n:.1f}% ({n - k}/{n})" if n >= 5 else f"{n - k}/{n}")
        cited = ""
        if t in m.index:
            if m.loc[t, "cited"]:
                cited = f"{_pct(100 * m.loc[t, 'cited_not_named'] / m.loc[t, 'cited'])}%"
        else:
            cited = "no reference paper"
        rows.append({
            "Package": packages.loc[packages["tool_id"] == t, "name"].iloc[0].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
            "Name type": NAME_TYPE.get(t, "distinctive"),
            "Query": query,
            "Precision of matches": cell,
            "False-positive rate": false_positive,
            "Wildcard additions that are other words": _n(kinds.loc[t, "other"]) if t in kinds.index else "",
            "Citing papers without a name match, 2021-2025 (%)": cited,
            "Of those, mention in article text (k/n, 2025)":
                f"{found.loc[t, 'k']}/{found.loc[t, 'n']}" if t in found.index else "",
        })
    return _md(pd.DataFrame(rows))


def citations() -> str:
    """Mentioning and citing per open-source package, 2021-2025, by how a citation was found."""
    y = pd.read_csv(PROCESSED_DIR / "mentions_citations_yearly.csv")
    y = y[y.year.between(2021, 2025) & y.tool_id.ne("nihimage")]
    t = y.groupby(["tool_id", "method"])[["named", "cited", "both"]].sum().reset_index()
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    t["union"] = t.named + t.cited - t.both
    t = t.sort_values(["method", "named"], ascending=[True, False])
    rows = [{"Package": names[r.tool_id].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
             "Citation found by": "link to own paper" if r.method == "links" else "reference title",
             "Mentioned": _n(r.named), "Cited": _n(r.cited), "Both": _n(r.both),
             "Mentioned, not cited (%)": _pct(100 * (r.named - r.both) / r.union),
             "Cited, not mentioned (%)": _pct(100 * (r.cited - r.both) / r.union)}
            for r in t.itertuples()]
    return _md(pd.DataFrame(rows))


def preprints() -> str:
    """Mentioned, not cited share in preprints and journal papers with a parsed reference list, 2021-2025."""
    d = pd.read_csv(PROCESSED_DIR / "citations_by_source_2021_2025.csv")
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    p = d[(d.reference_list == "parsed") & ~d.tool_id.isin(["microscopy", "nihimage"])].copy()
    p["nnc"] = 100 * (p.named - p.both) / (p.named + p.cited - p.both)
    w = p.pivot(index="tool_id", columns="source", values=["named", "nnc"])
    w = w.sort_values(("named", "journal"), ascending=False)
    # three columns: rxiv-maker gives tables of five columns one stretching column, which crushes this one
    rows = [{"Package": names[t].replace(" / ", "/").replace("ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"),
             "Preprints, n (not cited, %)": f"{_n(r[('named', 'preprint')])} ({_pct(r[('nnc', 'preprint')])})",
             "Journal papers, n (not cited, %)": f"{_n(r[('named', 'journal')])} ({_pct(r[('nnc', 'journal')])})"}
            for t, r in w.iterrows()]
    c = d[d.tool_id == "microscopy"].set_index(["source", "reference_list"])["named"]
    rows.append({"Package": "Parsed reference lists (%)",
                 "Preprints, n (not cited, %)": _pct(100 * c[("preprint", "parsed")] / c[("preprint", "all")]),
                 "Journal papers, n (not cited, %)": _pct(100 * c[("journal", "parsed")] / c[("journal", "all")])})
    return _md(pd.DataFrame(rows))


def drake() -> str:
    """Downloads, citations and Drake-equation ratios for estimable packages."""
    data = pd.read_csv(PROCESSED_DIR / "drake_2021_2025.csv")
    data = data[data.estimable]
    names = pd.read_csv(PROCESSED_DIR / "tools.csv").set_index("tool_id")["name"]
    columns = ["Package", "Source", "Downloads", "Citations", "C",
               "Per citing paper", "Per mention or citation"]
    rows = []
    for r in data.itertuples(index=False):
        package = names[r.tool_id].replace(" / ", "/").replace(
            "ZeroCostDL4Mic/DL4MicEverywhere", "ZCDL4M/DL4ME"
        )
        source = "image.sc, 2020" if r.tool_id == "imagej" else r.download_record
        rows.append({
            "Package": package,
            "Source": source,
            "Downloads": _n(r.downloads),
            "Citations": _n(r.citations),
            "C": f"{r.c_measured:.2f}",
            "Per citing paper": f"{r.downloads_per_citing_paper:.1f}",
            "Per mention or citation": f"{r.downloads_per_mention_or_citation:.1f}",
        })
    return _md(pd.DataFrame(rows, columns=columns))


TABLES = {"registry": registry, "methods_micro": methods_micro, "literature": literature, "adoption": adoption,
          "deep_learning": deep_learning, "methods_section": methods_section,
          "validation": validation, "reporting": reporting, "audit_area": audit_area, "mesh": mesh,
          "wildcard": wildcard, "queryerrors": queryerrors, "citations": citations,
          "preprints": preprints, "drake": drake}


def write_standalone() -> None:
    """Without the manuscript checkout, write every table to one local Markdown file."""
    parts = []
    for key, fn in TABLES.items():
        try:
            parts.append(f"## {key}\n\n{fn()}\n")
        except (KeyError, AttributeError, FileNotFoundError) as exc:
            print(f"[skip] {key}: {exc}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(parts))
    print(f"[tables] {OUTPUT}")


def main() -> None:
    if not SI.is_file():
        write_standalone()
        return
    text = SI.read_text()
    for key, fn in TABLES.items():
        pat = re.compile(rf"(<!-- TABLE:{key} START -->\n)(?:.*?\n)?(<!-- TABLE:{key} END -->)", re.S)
        if not pat.search(text):
            print(f"[skip] no markers for {key}")
            continue
        try:
            body = fn()
        except (KeyError, AttributeError, FileNotFoundError) as exc:
            print(f"[skip] {key}: {exc}")
            continue
        text = pat.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text)
        print(f"[table] {key}")
    SI.write_text(text)


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description="Rewrite the table blocks in MANUSCRIPT/02_SUPPLEMENTARY_INFO.md, or write "
                            "tables/output/supplementary_tables.md without the manuscript "
                            f"({', '.join(TABLES)}) from data/processed/.").parse_args()
    main()
