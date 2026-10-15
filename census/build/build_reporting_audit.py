"""Reporting audit: how completely 2025 Methods sections describe each package's use.

For six packages, a seeded random sample of open-access 2025 microscopy papers
that name the package in their Methods section (Europe PMC METHODS field). For
each paper, the full-text XML is read, citation markers are removed, the
Methods sections are located, and every sentence naming the package is taken
together with the sentence that follows it (the mention window). Fixed text
patterns then record four indicators:

  version    a software version next to the package name ("Fiji 2.14.0",
             "QuPath v0.5.1", "ImageJ 1.54f", "Cellpose version 3")
  function   a named plugin, command, module or model ("Analyze Particles",
             "IdentifyPrimaryObjects", "cyto3", "2D_versatile_fluo")
  parameter  a parameter with its value, a named thresholding method, or an
             explicit statement that default settings were used
  code       anywhere in the article, a code-hosting link, an analysis file
             (.ijm, .cppipe, .groovy, .ipynb) or a statement that code,
             scripts, macros or pipelines are available (not "on request")

No model labels these indicators; the patterns are listed below and checked
against an independent annotation sample (data/validation/).

Writes:
  data/processed/reporting_audit_2025.csv          per-tool rates, Wilson 95% CI
  data/processed/reporting_audit_papers_2025.csv   per-paper flags (no text)
  data/raw/reporting_audit/windows_2025.jsonl      mention windows (gitignored)

Run:  python -m census.build.build_reporting_audit [--n 200] [--tools imagej,qupath]
      python -m census.build.build_reporting_audit --selftest
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from census._http import USER_AGENT, get_json  # noqa: E402
from census._paths import PROCESSED_DIR, RAW_DIR, ensure_dirs  # noqa: E402
from census._registry import load_registry  # noqa: E402

YEAR = 2025
SEED = 20261006
TOOLS = ["imagej", "qupath", "cellprofiler", "napari", "cellpose", "stardist"]
SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
XML_DIR = RAW_DIR / "europepmc_fulltext"
OUT_RAW = RAW_DIR / "reporting_audit"

# --------------------------------------------------------------------------
# Sampling frame
# --------------------------------------------------------------------------


def frame_query(tool, context: str) -> str:
    methods = " OR ".join(tool.terms("METHODS:"))
    return f"({methods}) AND {context} AND OPEN_ACCESS:Y AND PUB_YEAR:{YEAR}"


def frame_pmcids(query: str) -> list[str]:
    ids, cursor = [], "*"
    while cursor:
        params = {"query": query, "format": "json", "resultType": "lite",
                  "pageSize": 1000, "cursorMark": cursor}
        data = get_json("europepmc", SEARCH, params)
        res = (data.get("resultList") or {}).get("result", [])
        if not res:
            break
        ids.extend(r["pmcid"] for r in res if r.get("pmcid"))
        nxt = data.get("nextCursorMark")
        cursor = nxt if nxt and nxt != cursor else None
    return sorted(set(ids))


# --------------------------------------------------------------------------
# Full text
# --------------------------------------------------------------------------

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})


def fetch_xml(pmcid: str) -> str | None:
    path = XML_DIR / f"{pmcid}.xml"
    if path.exists():
        txt = path.read_text()
        return txt or None
    for attempt in range(6):
        try:
            r = _SESSION.get(FULLTEXT.format(pmcid=pmcid), timeout=60)
            if r.status_code == 404:
                path.write_text("")
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            r.raise_for_status()
            path.write_text(r.text)
            time.sleep(0.15)
            return r.text
        except requests.RequestException:
            time.sleep(min(60, 2 ** (attempt + 1)))
    return None


_METHODS_TITLE = re.compile(
    r"(?i)\b(methods?|materials?|experimental procedures?|procedures|star\s*methods|"
    r"online methods|methodology)\b")
_SUP_CITE = re.compile(r"^[\s\d,\u2013\u2014\-\[\]()]+$")


def _strip_citations(root: ET.Element) -> None:
    """Empty bibliographic cross-references and bare superscript citation numbers,
    keeping the text that follows them, so "Cellpose<sup>4</sup>" reads "Cellpose"."""
    for el in root.iter():
        rt = el.get("ref-type")
        if (el.tag == "xref" and rt in ("bibr", "fn")) or (
                el.tag == "sup" and _SUP_CITE.match("".join(el.itertext()) or "x")):
            for child in list(el):
                el.remove(child)
            el.text = ""


def _text(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _blocks(sec: ET.Element) -> list[str]:
    """Paragraphs and table rows of a section, each as one text block."""
    out = []
    for el in sec.iter():
        if el.tag == "p":
            # skip paragraphs inside table cells; rows are taken whole below
            out.append(_text(el))
        elif el.tag == "tr":
            out.append(" ; ".join(_text(c) for c in el if c.tag in ("td", "th")))
    return [b for b in out if b]


def methods_sections(root: ET.Element) -> list[ET.Element]:
    found: list[ET.Element] = []

    def walk(el: ET.Element) -> None:
        for child in el:
            if child.tag == "sec" and child.get("sec-type") != "supplementary-material":
                title = child.findtext("title") or ""
                st = child.get("sec-type") or ""
                if "method" in st or "material" in st or _METHODS_TITLE.search(title):
                    found.append(child)
                    continue
            walk(child)

    walk(root)
    return found


_ABBREV = re.compile(
    r"\b(et al|e\.g|i\.e|Fig|Figs|Ref|Refs|Inc|Ltd|Co|vs|approx|ca|cf|No|Dr|Eq|Suppl|ver|resp)\.",
    re.I)
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


def sentences(block: str) -> list[str]:
    protected = _ABBREV.sub(lambda m: m.group(0)[:-1] + "\u2024", block)
    return [s.replace("\u2024", ".") for s in _SPLIT.split(protected) if s.strip()]


def alias_re(aliases: list[str]) -> re.Pattern:
    alt = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z])({alt})(?![A-Za-z])", re.I)


def mention_windows(blocks: list[str], areg: re.Pattern) -> list[str]:
    """Each sentence naming the package, joined to the sentence after it."""
    wins = []
    for b in blocks:
        ss = sentences(b)
        for i, s in enumerate(ss):
            if areg.search(s):
                wins.append(s + (" " + ss[i + 1] if i + 1 < len(ss) else ""))
    return wins


# --------------------------------------------------------------------------
# Indicators
# --------------------------------------------------------------------------

_UNIT = (r"(?:\u00b5m|\u03bcm|um|nm|mm|cm|%|px|pixels?|min|mins|h|hr|hrs|s|ms|sec|"
         r"x|\u00d7|mg|ml|mL|\u00b5l|\u03bcl|M|mM|\u00b5M|\u03bcM|nM|kDa|Hz|days?|weeks?|"
         r"cells?|images?|frames?|fields?|samples?|replicates?|slices?|\u00b0C?)")
# version token straight after the package name: "Fiji 2.14.0", "QuPath (v0.5.1)",
# "Cellpose 3", "cellpose==3.1", "Fiji (ImageJ 1.54f)"
_VER_AFTER = re.compile(
    rf"^[\s(\[,=:/-]*(?:(?:ImageJ2?|Fiji)\s*)?(?:version|ver\.?|release|v\.?)?\s*"
    rf"(\d+(?:\.\d+)*[a-z]?)\b(?!\s*{_UNIT}\b)(?!\.\d)", re.I)
_VER_KW = re.compile(r"(?i)\b(?:version|ver\.?|release)\s*:?\s*\d+(?:\.\d+)*[a-z]?\b|"
                     r"\bv\.?\s?\d+(?:\.\d+)+[a-z]?\b")
_IJ1_VER = re.compile(r"\b1\.\d{2}[a-z]\b")


def has_version(win: str, areg: re.Pattern, tool: str) -> bool:
    for m in areg.finditer(win):
        if _VER_AFTER.match(win[m.end(): m.end() + 30]):
            return True
        lo, hi = max(0, m.start() - 60), m.end() + 80
        if _VER_KW.search(win[lo:hi]):
            return True
    return tool == "imagej" and bool(_IJ1_VER.search(win))


_MENU = r"(?:Analy[sz]e|Process|Image|Plugins|Edit)\s*[>\u203a\u00bb\u2192|/]\s*[A-Z]"
_QUOTED = r"[\"\u201c\u2018'][A-Z][A-Za-z0-9 ()-]{2,40}[\"\u201d\u2019']"
FUNCTION = {
    "imagej": [_MENU, _QUOTED,
               r"\b(TrackMate|Bio-?Formats|Coloc ?2|JACoP|MorphoLibJ|Trainable Weka|Weka|"
               r"Analy[sz]e ?Skeleton|Skeletoni[sz]e|StarDist|Cellpose|ThunderSTORM|NanoJ|SRRF|"
               r"Simple Neurite Tracer|SNT|BoneJ|MOSAIC|ComDet|Find Maxima|Analy[sz]e Particles|"
               r"Particle Analy[sz]er|Cell Counter|Colocali[sz]ation Threshold|Auto ?Threshold|"
               r"Auto Local Threshold|Subtract Background|Rolling[- ]ball|Gaussian Blur|"
               r"Z[- ]?Project(?:ion)?|Ridge Detection|Directionality|OrientationJ|Sholl|"
               r"Set Measurements|Plot Profile|Watershed|Despeckle|Stitching|BigStitcher|"
               r"Correct 3D Drift|StackReg|TurboReg|Manual Tracking|MTrackJ|CLIJ2?|labkit|LabKit)\b"],
    "qupath": [_QUOTED,
               r"(?i)\b((?:positive |watershed )?cell detection|pixel classifier|object classifier|"
               r"(?:simple )?tissue detection|subcellular (?:spot )?detection|StarDist|Cellpose|"
               r"WSInfer|InstanSeg|Groovy|random trees|train(?:ed)? (?:an? )?(?:object |pixel )?classifier|"
               r"Analy[sz]e\s*>|Classify\s*>)"],
    "cellprofiler": [_QUOTED,
                     r"(?i)\b(Identify ?Primary ?Objects|Identify ?Secondary ?Objects|"
                     r"Identify ?Tertiary ?Objects|Measure ?Object ?Intensity(?: ?Distribution)?|"
                     r"Measure ?Object ?Size ?Shape|Measure ?Image ?Intensity|Measure ?Texture|"
                     r"Measure ?Colocali[sz]ation|Measure ?Granularity|Relate ?Objects|"
                     r"Export ?To ?Spreadsheet|Export ?To ?Database|Correct ?Illumination\w*|"
                     r"Mask ?Objects|Filter ?Objects|Track ?Objects|Run ?Cellpose|Run ?StarDist|"
                     r"Enhance ?Or ?Suppress ?Features|\.cppipe|\.cpproj)\b"],
    "napari": [_QUOTED,
               r"(?i)(\bnapari-[A-Za-z0-9][A-Za-z0-9-]+|\bmicro-?sam\b|segment anything|\bAPOC\b|"
               r"\bplug-?ins?\b|\bStarDist\b|\bCellpose\b|\bbtrack\b|\bLabkit\b)"],
    "cellpose": [r"(?i)\b(cyto3|cyto2|cpsam|tissuenet|livecell|Cellpose-SAM|CPx)\b",
                 r"(?i)[\"\u201c\u2018'`]?\b(cyto|nuclei|cytoplasm(?:ic)?)\b[\"\u201d\u2019'`]?\s*"
                 r"(?:\(\w+\)\s*)?(?:model|pretrained|pre-trained)",
                 r"(?i)model(?:_type)?\s*[=:]\s*[\"\u201c\u2018'`]?\w+",
                 r"(?i)\b(custom(?:-| )?(?:trained )?model|fine-?tun\w*|re-?train\w*|"
                 r"trained (?:a|our|the|on)|human-in-the-loop)"],
    "stardist": [r"(?i)\b(2D_versatile_fluo|2D_versatile_he|2D_paper_dsb2018|3D_demo|"
                 r"versatile[ (]*(?:fluo\w*|H&E|he)\b)",
                 r"(?i)\b(custom(?:-| )?(?:trained )?model|fine-?tun\w*|re-?train\w*|"
                 r"trained (?:a|our|the|on))"],
}

_PARAM = re.compile(
    r"(?i)\b(threshold|diameter|sigma|radius|rolling[- ]ball|circularity|prominence|tolerance|"
    r"flow[_ ]?threshold|cell ?prob\w*|prob(?:ability)?[_ ]?thresh\w*|nms|overlap|"
    r"min(?:imum)?[_ ]?(?:size|area)|max(?:imum)?[_ ]?(?:size|area)|"
    r"(?:size|area) (?:range|filter|cut-?off|threshold)|stitch threshold)\b[^.;]{0,40}?\d")
_THRESH_METHOD = re.compile(
    r"(?i)\bOtsu\b|\b(Huang|Triangle|IsoData|MaxEntropy|RenyiEntropy|Yen|Moments|Li|Default|"
    r"Intermodes|Minimum|Mean)\b\W+(?:\w+\W+){0,3}?thresh|thresh\w*\W+(?:\w+\W+){0,3}?"
    r"(Huang|Triangle|IsoData|MaxEntropy|RenyiEntropy|Yen|Moments|Li|Intermodes)\b")
_DEFAULTS = re.compile(r"(?i)\bdefault (?:parameters|settings|values|options)\b")

_CODE = re.compile(
    r"(?i)(github\.com|gitlab\.|bitbucket\.org|\.(?:ijm|cppipe|cpproj|groovy|ipynb)\b|"
    r"\b(?:macros?|scripts?|code|pipelines?|notebooks?)\b[^.]{0,80}?\b(?:available|deposited|"
    r"provided|included|accessible|shared)\b(?![^.]{0,60}\brequest))")


def indicators(wins: list[str], full_text: str, areg: re.Pattern, tool: str) -> dict:
    w = " || ".join(wins)
    return {
        "version": any(has_version(x, areg, tool) for x in wins),
        "function": any(re.search(p, w) for p in FUNCTION[tool]),
        "parameter": bool(_PARAM.search(w) or _THRESH_METHOD.search(w) or _DEFAULTS.search(w)),
        "code": bool(_CODE.search(full_text)),
    }


# --------------------------------------------------------------------------
# Per paper
# --------------------------------------------------------------------------


def audit_paper(pmcid: str, tool: str, areg: re.Pattern) -> dict:
    row = {"pmcid": pmcid, "tool_id": tool, "fetched": False, "scope": "none",
           "n_windows": 0, "version": False, "function": False, "parameter": False,
           "code": False, "windows": []}
    xml = fetch_xml(pmcid)
    if not xml:
        return row
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return row
    row["fetched"] = True
    _strip_citations(root)
    secs = methods_sections(root)
    wins = mention_windows([b for s in secs for b in _blocks(s)], areg)
    scope = "methods" if wins else "none"
    if not wins:
        body = root.find(".//body")
        if body is not None:
            wins = mention_windows(_blocks(body), areg)
            scope = "body" if wins else "none"
    full = _text(root)
    row.update(scope=scope, n_windows=len(wins), windows=wins)
    if wins:
        row.update(indicators(wins, full, areg, tool))
    return row


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main(n: int, tools: list[str]) -> None:
    ensure_dirs()
    XML_DIR.mkdir(parents=True, exist_ok=True)
    OUT_RAW.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    ctx = f"({reg.context_query})"
    rows, summary = [], []
    for tool in tools:
        t = reg.by_id(tool)
        areg = alias_re(t.aliases)
        frame = frame_pmcids(frame_query(t, ctx))
        rng = random.Random(f"{SEED}-{tool}-reporting")
        chosen = frame if len(frame) <= n else sorted(rng.sample(frame, n))
        print(f"[{tool}] frame {len(frame)}, sampling {len(chosen)}", flush=True)
        with ThreadPoolExecutor(max_workers=4) as ex:
            res = list(ex.map(lambda p, a=areg, tl=tool: audit_paper(p, tl, a), chosen))
        rows.extend(res)
        ok = [r for r in res if r["scope"] != "none"]
        rec = {"tool_id": tool, "name": t.name, "year": YEAR, "frame": len(frame),
               "sampled": len(chosen), "fetched": sum(r["fetched"] for r in res),
               "analysed": len(ok),
               "in_methods_text": sum(r["scope"] == "methods" for r in res)}
        for ind in ("version", "function", "parameter", "code"):
            k = sum(r[ind] for r in ok)
            lo, hi = wilson(k, len(ok))
            rec.update({f"{ind}_n": k, f"{ind}_pct": 100 * k / len(ok) if ok else float("nan"),
                        f"{ind}_lo": 100 * lo, f"{ind}_hi": 100 * hi})
        k = sum(r["version"] and (r["function"] or r["parameter"]) for r in ok)
        lo, hi = wilson(k, len(ok))
        rec.update({"complete_n": k, "complete_pct": 100 * k / len(ok) if ok else float("nan"),
                    "complete_lo": 100 * lo, "complete_hi": 100 * hi})
        k = sum(not (r["version"] or r["function"] or r["parameter"]) for r in ok)
        rec.update({"name_only_n": k, "name_only_pct": 100 * k / len(ok) if ok else float("nan")})
        summary.append(rec)
        print({k: (round(v, 1) if isinstance(v, float) else v) for k, v in rec.items()}, flush=True)
    with open(OUT_RAW / f"windows_{YEAR}.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps({k: r[k] for k in ("pmcid", "tool_id", "scope", "windows")}) + "\n")
    flat = pd.DataFrame([{k: v for k, v in r.items() if k != "windows"} for r in rows])
    flat.to_csv(PROCESSED_DIR / f"reporting_audit_papers_{YEAR}.csv", index=False)
    pd.DataFrame(summary).to_csv(PROCESSED_DIR / f"reporting_audit_{YEAR}.csv", index=False)
    print("wrote", PROCESSED_DIR / f"reporting_audit_{YEAR}.csv")


# --------------------------------------------------------------------------
# Self-test of the patterns on hand-written sentences
# --------------------------------------------------------------------------

CASES = [
    ("imagej", "Images were analysed in Fiji (ImageJ 1.54f).", dict(version=True)),
    ("imagej", "Images were analysed with Fiji 2.14.0 using Analyze Particles.", dict(version=True, function=True)),
    ("imagej", "Images were analysed in ImageJ.", dict(version=False, function=False, parameter=False)),
    ("imagej", "ImageJ was used to count 50 cells per image.", dict(version=False)),
    ("imagej", "In Fiji, Process > Subtract Background with a rolling ball radius of 50 pixels.", dict(function=True, parameter=True)),
    ("imagej", "Thresholds were set with the Otsu method in ImageJ.", dict(parameter=True)),
    ("qupath", "QuPath (v0.5.1) positive cell detection was run with default settings.", dict(version=True, function=True, parameter=True)),
    ("qupath", "Slides were scanned and viewed in QuPath.", dict(version=False, function=False, parameter=False)),
    ("cellprofiler", "CellProfiler 4.2.6 IdentifyPrimaryObjects segmented nuclei (diameter 15-60 pixels).", dict(version=True, function=True, parameter=True)),
    ("napari", "Masks were inspected in napari using the napari-animation plugin.", dict(function=True, version=False)),
    ("cellpose", "Cells were segmented with Cellpose 3 using the cyto3 model and a diameter of 30 pixels.", dict(version=True, function=True, parameter=True)),
    ("cellpose", "Nuclei were segmented with Cellpose.", dict(version=False, function=False, parameter=False)),
    ("cellpose", "We used the nuclei model of Cellpose (version 2.0).", dict(version=True, function=True)),
    ("stardist", "Nuclei were detected with StarDist (2D_versatile_fluo, probability threshold 0.5).", dict(function=True, parameter=True)),
    ("stardist", "StarDist segmented 200 nuclei per field.", dict(version=False, parameter=False)),
]


def selftest() -> None:
    reg = load_registry()
    bad = 0
    for tool, sent, expect in CASES:
        areg = alias_re(reg.by_id(tool).aliases)
        got = indicators(mention_windows([sent], areg), sent, areg, tool)
        for k, v in expect.items():
            if got[k] != v:
                bad += 1
                print(f"FAIL {tool} {k}: expected {v}, got {got[k]} :: {sent}")
    xml = ('<article><body><sec><title>Methods</title><p>Cells were segmented with '
           'Cellpose<xref ref-type="bibr">4</xref> in Fiji<sup>12</sup>.</p></sec></body></article>')
    root = ET.fromstring(xml)
    _strip_citations(root)
    blocks = [b for s in methods_sections(root) for b in _blocks(s)]
    if blocks != ["Cells were segmented with Cellpose in Fiji."]:
        bad += 1
        print("FAIL citation stripping:", blocks)
    print(f"{len(CASES)} cases + citation stripping: {'all pass' if not bad else f'{bad} failures'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--tools", default=",".join(TOOLS))
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--replicates", action="store_true",
                    help="write disjoint replicate rates only; leave the 2025 outputs unchanged")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.replicates:
        from census.validation.replicates import audit
        audit(n=a.n, tools=a.tools.split(","))
    else:
        main(a.n, a.tools.split(","))
