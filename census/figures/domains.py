"""Research areas of each tool's applications, from every paper or a random sample.

The corpus is the simple random sample drawn for the deep-learning estimate
(scripts/data/processed/random_sample_2021_2025.csv.gz), restricted to 2021-2025
so every main tool is compared over the same years. Each paper is weighted by
population / sampled size of its tool-year, so a tool's share estimates the
share of all its 2021-2025 matches.

Enrichment compares a tool's share with a leave-one-out baseline: the pooled
matches of every other dedicated tool, weighted the same way. The baseline is
dominated by ImageJ/Fiji, which reaches a quarter of microscopy papers, so it
approximates the microscopy literature that names analysis software.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import pandas as pd
# English stop words copied from scikit-learn 1.8.0 (sklearn/feature_extraction/_stop_words.py),
# so the figure scripts do not depend on scikit-learn.
# Authors: The scikit-learn developers
# SPDX-License-Identifier: BSD-3-Clause
# The list is taken from the Glasgow Information Retrieval Group; see THIRD_PARTY_NOTICES.md.
ENGLISH_STOP_WORDS = frozenset("""
    a about above across after afterwards again against all almost alone along already
    also although always am among amongst amoungst amount an and another any anyhow
    anyone anything anyway anywhere are around as at back be became because become
    becomes becoming been before beforehand behind being below beside besides between
    beyond bill both bottom but by call can cannot cant co con could couldnt cry de
    describe detail do done down due during each eg eight either eleven else elsewhere
    empty enough etc even ever every everyone everything everywhere except few fifteen
    fifty fill find fire first five for former formerly forty found four from front
    full further get give go had has hasnt have he hence her here hereafter hereby
    herein hereupon hers herself him himself his how however hundred i ie if in inc
    indeed interest into is it its itself keep last latter latterly least less ltd made
    many may me meanwhile might mill mine more moreover most mostly move much must my
    myself name namely neither never nevertheless next nine no nobody none noone nor
    not nothing now nowhere of off often on once one only onto or other others
    otherwise our ours ourselves out over own part per perhaps please put rather re
    same see seem seemed seeming seems serious several she should show side since
    sincere six sixty so some somehow someone something sometime sometimes somewhere
    still such system take ten than that the their them themselves then thence there
    thereafter thereby therefore therein thereupon these they thick thin third this
    those though three through throughout thru thus to together too top toward towards
    twelve twenty two un under until up upon us very via was we well were what whatever
    when whence whenever where whereafter whereas whereby wherein whereupon wherever
    whether which while whither who whoever whole whom whose why will with within
    without would yet you your yours yourself yourselves
""".split())

from . import style as fs

# Every alternative starts at a word boundary; stems are listed explicitly so
# method words (immunofluorescence, polymerase, delivery) cannot match.
DOMAINS = {
    "Neuroscience": r"\b(?:neurons?\b|neuronal|neurodegen|neuroinflamm|neurodevelop|neurotransmi|brain|synap|axon|dendrit(?!ic cells?)|cerebral cortex|cortical neuron|cortical circuit|cortical layer|cortical development|hippocamp|astrocyt|microglia|glia\b|glial|oligodendro|spinal cord|retina)",
    "Cancer": r"\b(?:cancers?\b|tumou?rs?\b|tumou?ral|carcinoma|adenocarcinoma|metasta|oncogen|melanoma|glioblastoma|glioma|leuka?emi|lymphoma|sarcoma|neoplas|antitumou?r)",
    "Immunology": r"\b(?:immune|immunity|immunolog|immunotherap|t[- ]cells?\b|b[- ]cells?\b|macrophag|lymphocyt|antigens?\b|inflamma|cytokines?|neutrophil|dendritic cells?|monocyt|interleukin|interferon)",
    "Microbiology and infection": r"\b(?:bacteri|virus|viral\b|virion|infect|pathogens?\b|pathogenic|sars-cov|covid|yeast|fungi|fungal|parasit|plasmodium|malaria|microbio|tubercul|mycobact|hiv\b|influenza)",
    "Development and organoids": r"\b(?:embryo|zebrafish|drosophila|developmental|morphogen|organogen|elegans|xenopus|gastrula|organoids?\b)",
    "Plant biology": r"\b(?:plants?\b|arabidopsis|leaf\b|leaves\b|chloroplast|seedlings?\b|photosynth|pollen|maize)",
    "Organelles and cytoskeleton": r"\b(?:mitochond|actin\b|f-actin|actomyosin|microtubul|cytoskelet|endosom|lysosom|autophag|golgi|endoplasmic reticulum|organelles?\b|vesicles?\b|centrosom|cilia\b|cilium|nuclear envelope)",
    "Clinical and pathology": r"\b(?:patients?\b|clinical|biops|diagnos|prognos|cohorts?\b|whole[- ]slide|histopatholog|pathologists?\b|digital pathology)",
    "Single-cell and spatial omics": r"\b(?:single[- ]cell (?:rna|sequencing|transcriptom|atlas|multi-?omic|proteom)|scrna|snrna|transcriptom|rna-seq|spatial(?:ly)? (?:resolved|transcriptom|proteom|omics)|merfish|seqfish|visium|xenium|imaging mass cytometry)",
    "Cardiovascular and renal": r"\b(?:cardiac|cardio|heart\b|vascular|endotheli|angiogen|atheroscl|blood vessels?|kidneys?\b|renal\b)",
    "Metabolic disease and liver": r"\b(?:diabet|obes|adipo|insulin|hepat|liver\b|steatosis)",
    "Electron microscopy": r"\b(?:cryo-?et\b|cryo-?electron|electron microscop|electron tomograph|fib-?sem|serial[- ]section|connectom|volume electron|volume em\b)",
    "Materials science": r"\b(?:nanoparticles?\b|nanomaterial|hydrogels?\b|polymers?\b|polymeric|graphene|alloys?\b|nanostruct|biomaterial)",
    "Computational methods": r"\b(?:segmentation|deep learning|machine learning|neural networks?\b|pipelines?\b|open-source|software|algorithms?\b|computational)",
}

GENERIC = set("""
cell cells study studies result results using used use uses based analysis analyses analyzed analysed
image images imaging microscopy microscope microscopic data method methods show shows shown showed
here found also however including include includes demonstrate demonstrated demonstrates identify
identified identifies reveal revealed reveals role roles function functions functional increase
increased decrease decreased level levels high higher low lower new novel model models type types
protein proteins expression expressed specific significantly significant different differences
within across two three one first may can well whereas via thus could might respectively
suggest suggests suggesting associated compared mechanism mechanisms process processes regulate
regulates regulated regulation response responses effect effects important key major multiple
provide provides approach approaches system systems present report reported total overall large
small number numbers time times formation form forms activity activities factor factors
mediated dependent induced induce induces human mouse mice vivo vitro understanding
lead leads leading potential required require requires contribute contributes contributing
structure structures structural state states dynamics rate rates change changes changed
molecular measured measure measurement measurements quantitative quantify quantified
control controls remain remains unknown poorly understood previously known
modulate modulates modulated mediate mediates governs findings finding furthermore moreover
enable enables enabled critical crucial distinct unique particular despite additionally
resulting observed observe performed performance various future recent
""".split())
TOOL_WORDS = set("""imagej imagej2 fiji cellprofiler qupath ilastik napari cellpose stardist icy knime
imaris arivis jupyter matlab deepimagej zerocostdl4mic dl4mic""".split())
STOP = set(ENGLISH_STOP_WORDS) | GENERIC | TOOL_WORDS
TOKEN = re.compile(r"[a-z][a-z0-9\-]{2,}")
TAG = re.compile(r"<[^>]+>")

MIN_PAPERS = 300


def load_corpus(tools=None) -> pd.DataFrame:
    """Prepare sampled rows, defaulting to the unchanged analysis-package corpus."""
    d = fs.load("random_sample_2021_2025.csv.gz").fillna("")
    d = d[d["tool_id"].isin(fs.analysis_tools() if tools is None else tools)].copy()
    d["text"] = (d["title"] + " " + d["abstract"]).map(lambda s: TAG.sub(" ", s).lower())
    d["w"] = d["population"] / d["n_sampled"].where(d["n_sampled"] > 0, 1)
    for k, p in DOMAINS.items():
        d[k] = d["text"].str.contains(p, regex=True)
    return d.reset_index(drop=True)


def _share(sub: pd.DataFrame, col: str) -> float:
    return float((sub[col] * sub["w"]).sum() / sub["w"].sum())


def enrichment(d: pd.DataFrame, n_boot: int = 500, seed: int = 1) -> pd.DataFrame:
    """Compute weighted package shares, leave-one-out baselines, ratios and 95% bootstrap intervals.

    Point estimates use the design weights; each replicate draws one Poisson(1)
    weight per distinct paper and applies it to that paper's sampled-stratum rows,
    while census-stratum rows keep a multiplier of 1.
    """
    rng = np.random.default_rng(seed)
    tools = [t for t, n in d["tool_id"].value_counts().items() if n >= MIN_PAPERS]
    paper_codes, papers = pd.factorize(d["epmc_id"], sort=False)
    sampled = d["n_sampled"].to_numpy() < d["population"].to_numpy()
    X = d[list(DOMAINS)].to_numpy(float)
    w = d["w"].to_numpy()
    tool = d["tool_id"].to_numpy()

    def shares(idx, weights=None):
        ww, xx, tt = (w if weights is None else weights)[idx], X[idx], tool[idx]
        tot_w = np.bincount(pd.factorize(tt, sort=True)[0], weights=ww)
        names = np.array(sorted(set(tt)))
        num = np.vstack([np.bincount(pd.factorize(tt, sort=True)[0], weights=ww * xx[:, j])
                         for j in range(xx.shape[1])]).T
        per = pd.DataFrame(num / tot_w[:, None], index=names, columns=list(DOMAINS))
        allw, alln = tot_w.sum(), num.sum(axis=0)
        loo = {t: (alln - num[i]) / (allw - tot_w[i]) for i, t in enumerate(names)}
        return per, pd.DataFrame(loo, index=list(DOMAINS)).T

    idx = np.arange(len(d))
    per, base = shares(idx)
    boots = []
    for _ in range(n_boot):
        paper_weights = rng.poisson(1, size=len(papers))
        multiplier = np.ones(len(d))
        multiplier[sampled] = paper_weights[paper_codes[sampled]]
        p, b = shares(idx, w * multiplier)
        boots.append((p / b.replace(0, np.nan)).loc[tools].to_numpy())
    boots = np.array(boots)
    rows = []
    for i, t in enumerate(tools):
        for j, k in enumerate(DOMAINS):
            r = boots[:, i, j]
            rows.append({"tool_id": t, "domain": k, "share": 100 * per.loc[t, k],
                         "baseline": 100 * base.loc[t, k],
                         "ratio": per.loc[t, k] / base.loc[t, k] if base.loc[t, k] else np.nan,
                         "lo": np.nanpercentile(r, 2.5), "hi": np.nanpercentile(r, 97.5),
                         "n": int((d["tool_id"] == t).sum())})
    return pd.DataFrame(rows)


def control_enrichment(n_boot: int = 500, seed: int = 1) -> pd.DataFrame:
    """Compare each microscope-control program with the analysis corpus alone.

    Add one control at a time so its leave-one-out baseline never includes
    another control. Shared papers retain enrichment's paper-level bootstrap.
    """
    registry = fs.load("tools.csv")
    controls = registry.loc[registry["category"] == "acquisition-suite", "tool_id"]
    analysis_tools = fs.analysis_tools()
    corpus = load_corpus([*analysis_tools, *controls])
    analysis = corpus[corpus["tool_id"].isin(analysis_tools)]
    results = []
    for tool in controls:
        rows = corpus[corpus["tool_id"] == tool]
        if len(rows) < MIN_PAPERS:
            continue
        combined = pd.concat([analysis, rows], ignore_index=True)
        result = enrichment(combined, n_boot=n_boot, seed=seed)
        results.append(result[result["tool_id"] == tool])
    return pd.concat(results, ignore_index=True) if results else pd.DataFrame(
        columns=["tool_id", "domain", "share", "baseline", "ratio", "lo", "hi", "n"])


PHRASES = [(r"\bdeep[\s-]+learning\b", "deep-learning"), (r"\bmachine[\s-]+learning\b", "machine-learning"),
           (r"\bwestern[\s-]+blot(?:s|ting)?\b", "western-blot"), (r"\blight[\s-]+sheet\b", "light-sheet"),
           (r"\bhigh[\s-]+throughput\b", "high-throughput"), (r"\bhigh[\s-]+content\b", "high-content"),
           (r"\bsingle[\s-]+cell\b", "single-cell"), (r"\bopen[\s-]+source\b", "open-source")]
HEADINGS = {"background", "conclusion", "conclusions", "objective", "objectives", "aim", "aims",
            "purpose", "introduction", "significance", "abstract", "summary"}
FOLD = {"microglial": "microglia", "blot": "western-blot", "blotting": "western-blot", "tumours": "tumor",
        "tumour": "tumor", "tumors": "tumor", "inhibited": "inhibit", "inhibiting": "inhibit",
        "inhibition": "inhibit"}


def _fold(w: str) -> str:
    w = FOLD.get(w, w)
    if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "is", "us", "ics")):
        w = w[:-1]
    return w


def doc_terms(text: str) -> set[str]:
    for pat, rep in PHRASES:
        text = re.sub(pat, rep, text)
    out = set()
    for w in TOKEN.findall(text):
        w = _fold(w.strip("-"))
        if w and w not in STOP and w not in HEADINGS and not w[0].isdigit():
            out.add(w)
    return out


def enriched_terms(d: pd.DataFrame, tool: str, min_share: float = 0.02, top: int = 8) -> pd.DataFrame:
    """Words over-represented in a tool's abstracts, with weighted prevalence.

    Prevalence is the weighted share of abstracts containing the word, for the
    tool and for the leave-one-out baseline. Only words in at least
    ``min_share`` of the tool's abstracts qualify, so rare words cannot lead.
    """
    terms = d["text"].map(doc_terms)
    inn = d["tool_id"] == tool
    def prev(mask):
        c = Counter()
        for ts, ww in zip(terms[mask], d.loc[mask, "w"]):
            for t in ts:
                c[t] += ww
        tot = d.loc[mask, "w"].sum()
        return {k: v / tot for k, v in c.items()}
    p_in, p_out = prev(inn), prev(~inn)
    n_in = int(inn.sum())
    rows = []
    for word, p in p_in.items():
        if p < min_share:
            continue
        q = p_out.get(word, 0.0)
        # log-odds with a +0.5 correction on the sample scale
        k_in, k_out = p * n_in, q * (~inn).sum()
        lo = math.log((k_in + .5) / (n_in - k_in + .5)) - math.log((k_out + .5) / ((~inn).sum() - k_out + .5))
        se = math.sqrt(1 / (k_in + .5) + 1 / (n_in - k_in + .5) + 1 / (k_out + .5) + 1 / ((~inn).sum() - k_out + .5))
        rows.append({"word": word, "tool_pct": 100 * p, "base_pct": 100 * q, "z": lo / se})
    return pd.DataFrame(rows).sort_values("z", ascending=False).head(top)


def build_enrichment(out_path=None, n_boot: int = 500, seed: int = 1) -> pd.DataFrame:
    """Rebuild the processed research-area table from the offline sample.

    Defaults reproduce the original figure's CSV byte for byte. Figure rendering
    only reads this table; rebuilding it is an explicit pipeline step.
    """
    out_path = fs.PROCESSED / "domain_enrichment.csv" if out_path is None else out_path
    result = enrichment(load_corpus(), n_boot=n_boot, seed=seed)
    result.to_csv(out_path, index=False)
    return result


def build_control_enrichment(out_path=None, n_boot: int = 500, seed: int = 1) -> pd.DataFrame:
    """Write microscope-control contrasts without changing the analysis table."""
    out_path = fs.PROCESSED / "domain_enrichment_control.csv" if out_path is None else out_path
    result = control_enrichment(n_boot=n_boot, seed=seed)
    result.to_csv(out_path, index=False)
    return result
