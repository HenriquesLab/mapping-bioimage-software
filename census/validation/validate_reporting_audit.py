"""Check the reporting-audit patterns against two independent annotators.

  python -m census.validation.validate_reporting_audit sample   # draw the annotation items
  python -m census.validation.validate_reporting_audit score    # compare patterns with labels

`sample` draws 10 analysed papers per tool (seeded) from the audit and writes,
for each, the tool's Methods mention windows and the article's statements that
could concern code: availability sections plus every sentence naming code,
scripts, macros, pipelines, notebooks or a repository. Annotators label the four
indicators from that text alone, without seeing the pattern results.

`score` reads one label file per annotator
(data/validation/reporting_audit_labels_<annotator>.csv: item_id, version,
function, parameter, code as 0/1) and writes, per indicator, the agreement and
Cohen's kappa between annotators and the precision and recall of the patterns
against the items where both annotators agree.
"""

from __future__ import annotations

import json
import random
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from census._paths import DATA_DIR, PROCESSED_DIR, RAW_DIR  # noqa: E402
from census.build.build_reporting_audit import (XML_DIR, YEAR, _strip_citations, _text,  # noqa: E402
                                   sentences)

IND = ["version", "function", "parameter", "code"]
OUT_RAW = RAW_DIR / "reporting_audit"
VAL_DIR = DATA_DIR / "validation"
PER_TOOL = 10
SEED = 20261006
_CODEISH = re.compile(r"(?i)\b(code|scripts?|macros?|pipelines?|notebooks?|github|gitlab|"
                      r"zenodo|figshare|bitbucket|software availability)\b|\.(ijm|cppipe|groovy|ipynb)\b")


def code_context(pmcid: str) -> str:
    xml = (XML_DIR / f"{pmcid}.xml").read_text()
    root = ET.fromstring(xml)
    _strip_citations(root)
    parts = []
    for sec in root.iter("sec"):
        if "availab" in (sec.findtext("title") or "").lower():
            parts.append(_text(sec))
    for p in root.iter("p"):
        for s in sentences(_text(p)):
            if _CODEISH.search(s):
                parts.append(s)
    seen, out = set(), []
    for x in parts:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return "\n".join(out)[:6000]


def sample() -> None:
    papers = pd.read_csv(PROCESSED_DIR / f"reporting_audit_papers_{YEAR}.csv")
    wins = {}
    for line in open(OUT_RAW / f"windows_{YEAR}.jsonl"):
        r = json.loads(line)
        wins[(r["pmcid"], r["tool_id"])] = r["windows"]
    rng = random.Random(SEED)
    items = []
    for tool, g in papers[papers["scope"] != "none"].groupby("tool_id", sort=False):
        ids = sorted(g["pmcid"])
        for pmcid in sorted(rng.sample(ids, min(PER_TOOL, len(ids)))):
            items.append({"item_id": f"{tool}-{pmcid}", "tool_id": tool, "pmcid": pmcid,
                          "methods_mentions": wins[(pmcid, tool)],
                          "code_context": code_context(pmcid)})
    with open(OUT_RAW / f"validation_items_{YEAR}.jsonl", "w") as fh:
        for it in items:
            fh.write(json.dumps(it) + "\n")
    print(f"wrote {len(items)} items to {OUT_RAW / f'validation_items_{YEAR}.jsonl'}")


def kappa(a: pd.Series, b: pd.Series) -> float:
    po = (a == b).mean()
    pa, pb = a.mean(), b.mean()
    pe = pa * pb + (1 - pa) * (1 - pb)
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)


def score() -> None:
    files = sorted(VAL_DIR.glob("reporting_audit_labels_*.csv"))
    if len(files) != 2:
        sys.exit(f"need exactly two label files, found {len(files)}")
    names = [f.stem.replace("reporting_audit_labels_", "") for f in files]
    a, b = (pd.read_csv(f).set_index("item_id") for f in files)
    papers = pd.read_csv(PROCESSED_DIR / f"reporting_audit_papers_{YEAR}.csv")
    papers["item_id"] = papers["tool_id"] + "-" + papers["pmcid"]
    pat = papers.set_index("item_id").loc[a.index, IND].astype(int)
    rows = []
    for ind in IND:
        x, y, p = a[ind].astype(int), b[ind].astype(int), pat[ind]
        agree = x == y
        ref = x[agree]
        pp = p[agree]
        tp = int(((pp == 1) & (ref == 1)).sum())
        fp = int(((pp == 1) & (ref == 0)).sum())
        fn = int(((pp == 0) & (ref == 1)).sum())
        rows.append({"indicator": ind, "items": len(x), "annotators": " vs ".join(names),
                     "annotator_agreement_pct": round(100 * agree.mean(), 1),
                     "kappa": round(kappa(x, y), 2), "consensus_items": int(agree.sum()),
                     "consensus_positive": int(ref.sum()), "pattern_tp": tp, "pattern_fp": fp,
                     "pattern_fn": fn,
                     "precision_pct": round(100 * tp / (tp + fp), 1) if tp + fp else None,
                     "recall_pct": round(100 * tp / (tp + fn), 1) if tp + fn else None,
                     "pattern_vs_consensus_agreement_pct": round(100 * (pp == ref).mean(), 1)})
    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED_DIR / f"reporting_audit_validation_{YEAR}.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["sample", "score"],
                    help="sample: draw the annotation items; score: compare patterns with labels")
    {"sample": sample, "score": score}[ap.parse_args().command]()
