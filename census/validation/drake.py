"""Compare download records with citations to bioimage analysis software.

PyPI counts use the Python Software Foundation's BigQuery data through
ClickHouse (CC BY 4.0); GitHub release counts use its public API; OpenAlex
citation counts are available under CC0. Fiji's reported count comes from image.sc.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

from census._http import CONTACT_EMAIL, USER_AGENT
from census._paths import CONFIG_DIR, PROCESSED_DIR, RAW_DIR, ensure_dirs
from census.sources.github import _headers as github_headers

YEARS = range(2020, 2026)
POOLED_YEARS = range(2021, 2026)
END_USER_INSTALLERS = ("pip", "uv", "poetry", "pdm", "pipenv")
PYPI_PROJECTS = {
    "cellpose": ("cellpose",),
    "stardist": ("stardist",),
    "cellprofiler": ("cellprofiler",),
    "napari": ("napari",),
    "skimage": ("scikit-image",),
    "opencv": ("opencv-python",),
    "jupyter": ("notebook", "jupyterlab"),
}
GITHUB_REPOS = {
    "qupath": ("qupath/qupath",),
    "cellprofiler": ("CellProfiler/CellProfiler",),
    "napari": ("napari/napari",),
}
ESTIMABLE = ("qupath", "cellpose", "stardist")
NOT_ESTIMABLE = {
    "cellprofiler": "installers mostly downloaded from cellprofiler.org, which publishes no counts",
    "ilastik": "installers downloaded from ilastik.org, which publishes no counts",
    "napari": "cited mainly through a software record",
    "skimage": "installed mostly as a dependency of other packages",
    "opencv": "installed mostly as a dependency of other packages",
    "jupyter": "installed mostly as a dependency of other packages",
}
PACKAGE_IDS = (*ESTIMABLE, *NOT_ESTIMABLE)
PYPI_URL = "https://sql-clickhouse.clickhouse.com/"
GITHUB_API = "https://api.github.com/repos/"
OPENALEX_API = "https://api.openalex.org/works/doi:"
CACHE_DIR = RAW_DIR / "drake"
PYPI_CACHE = CACHE_DIR / "pypi.json"
GITHUB_CACHE = CACHE_DIR / "github.json"
OPENALEX_CACHE = CACHE_DIR / "openalex.json"
POOLED_CSV = PROCESSED_DIR / "drake_2021_2025.csv"
YEARLY_CSV = PROCESSED_DIR / "drake_yearly.csv"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def _fetch_pypi(retrieved_at: str) -> dict:
    """Fetch annual PyPI totals for each configured project via ClickHouse."""
    project_tools = {project: tool for tool, projects in PYPI_PROJECTS.items() for project in projects}
    projects = tuple(project_tools)
    project_sql = ", ".join(f"'{project}'" for project in projects)
    installers_sql = ", ".join(f"'{installer}'" for installer in END_USER_INSTALLERS)
    sql = (
        "SELECT project, toYear(date) AS year, count() AS all_installers, "
        f"countIf(installer IN ({installers_sql})) AS end_user_installers "
        "FROM pypi.pypi "
        f"WHERE project IN ({project_sql}) AND date >= '2020-01-01' AND date < '2026-01-01' "
        "GROUP BY project, year ORDER BY project, year FORMAT JSONEachRow"
    )
    response = requests.post(
        PYPI_URL, params={"user": "play"}, data=sql,
        headers={"User-Agent": USER_AGENT, "Content-Type": "text/plain"}, timeout=180,
    )
    response.raise_for_status()
    packages = {
        tool: {
            str(year): {"all_installers": 0, "end_user_installers": 0}
            for year in YEARS
        }
        for tool in PYPI_PROJECTS
    }
    for line in response.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        tool = project_tools[row["project"]]
        year = str(int(row["year"]))
        packages[tool][year]["all_installers"] += int(row["all_installers"])
        packages[tool][year]["end_user_installers"] += int(row["end_user_installers"])
    return {
        "retrieved_at": retrieved_at,
        "projects": {tool: list(projects) for tool, projects in PYPI_PROJECTS.items()},
        "end_user_installers": list(END_USER_INSTALLERS),
        "packages": packages,
    }


def _fetch_github(retrieved_at: str) -> dict:
    """Fetch release-asset download counts, grouped by published year."""
    repositories: dict[str, dict[str, int]] = {}
    packages: dict[str, dict[str, int]] = {}
    headers = github_headers()
    for tool, repos in GITHUB_REPOS.items():
        packages[tool] = {str(year): 0 for year in YEARS}
        for repo in repos:
            yearly = {str(year): 0 for year in YEARS}
            url = f"{GITHUB_API}{repo}/releases"
            params: dict[str, int] | None = {"per_page": 100}
            while url:
                response = requests.get(url, params=params, headers=headers, timeout=60)
                response.raise_for_status()
                releases = response.json()
                if not isinstance(releases, list):
                    raise ValueError(f"Expected a release list from GitHub for {repo}")
                for release in releases:
                    published = release.get("published_at") or ""
                    year = published[:4]
                    if year not in yearly:
                        continue
                    yearly[year] += sum(
                        int(asset.get("download_count") or 0)
                        for asset in release.get("assets") or []
                    )
                url = response.links.get("next", {}).get("url", "")
                params = None
            repositories[repo] = yearly
            for year, count in yearly.items():
                packages[tool][year] += count
    return {"retrieved_at": retrieved_at, "repositories": repositories, "packages": packages}


def _openalex_work(doi: str) -> dict | None:
    """Fetch one OpenAlex work; return None only when the DOI is unresolved."""
    url = f"{OPENALEX_API}{doi}"
    params = {"select": "id,counts_by_year", "mailto": CONTACT_EMAIL}
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=60
            )
            if response.status_code == 404:
                return None
            if response.status_code in (429, 502, 503, 504):
                time.sleep(min(30, 2 ** attempt))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"OpenAlex request failed after 5 tries: {doi}") from last_error


def _fetch_openalex(retrieved_at: str) -> dict:
    """Fetch and sum yearly OpenAlex citations for configured software papers."""
    papers = yaml.safe_load((CONFIG_DIR / "package_papers.yml").read_text())
    packages: dict[str, dict] = {}
    missing_dois = []
    for tool, dois in papers.items():
        yearly = {str(year): 0 for year in YEARS}
        for doi in dois or []:
            work = _openalex_work(doi)
            if work is None:
                missing_dois.append({"tool_id": tool, "doi": doi})
            else:
                for count in work.get("counts_by_year") or []:
                    year = str(count.get("year", ""))
                    if year in yearly:
                        yearly[year] += int(count.get("cited_by_count") or 0)
            time.sleep(0.2)
        packages[tool] = {"dois": dois or [], "years": yearly}
    return {"retrieved_at": retrieved_at, "packages": packages, "missing_dois": missing_dois}


def fetch() -> None:
    """Fetch PyPI, GitHub and OpenAlex counts into the local raw cache."""
    ensure_dirs()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    retrieved_at = dt.date.today().isoformat()
    _write_json(PYPI_CACHE, _fetch_pypi(retrieved_at))
    _write_json(GITHUB_CACHE, _fetch_github(retrieved_at))
    _write_json(OPENALEX_CACHE, _fetch_openalex(retrieved_at))
    print(f"Fetched Drake sources on {retrieved_at}")


def _load_cache(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing Drake cache {path}; run with --fetch first")
    return json.loads(path.read_text())


def _sum_years(years: dict, field: str | None = None, selected=POOLED_YEARS) -> int:
    if field is None:
        return sum(int(years.get(str(year), 0) or 0) for year in selected)
    return sum(
        int((years.get(str(year), {}) or {}).get(field, 0) or 0)
        for year in selected
    )


def _citation_measure() -> dict[str, float]:
    mentions = pd.read_csv(PROCESSED_DIR / "mentions_citations_yearly.csv")
    mentions = mentions[mentions.year.between(2021, 2025)]
    totals = mentions.groupby("tool_id")[["named", "cited", "both"]].sum()
    result = {}
    for tool, row in totals.iterrows():
        result[tool] = (
            float((row.named + row.cited - row.both) / row.cited)
            if row.cited else float("nan")
        )
    return result


def _pooled_row(
    tool: str, pypi: dict, github: dict, openalex: dict, c_measured: dict
) -> dict:
    pypi_years = pypi.get("packages", {}).get(tool, {})
    github_years = github.get("packages", {}).get(tool, {})
    openalex_years = openalex.get("packages", {}).get(tool, {}).get("years", {})
    downloads_pypi = _sum_years(pypi_years, "end_user_installers")
    downloads_github = _sum_years(github_years)
    downloads = downloads_pypi + downloads_github
    citations = _sum_years(openalex_years)
    c = c_measured.get(tool, float("nan"))
    estimable = tool in ESTIMABLE
    reason = NOT_ESTIMABLE.get(tool, "")
    download_record = (
        "GitHub installers" if tool == "qupath" else "PyPI" if tool in {"cellpose", "stardist"}
        else reason
    )
    citing_ratio = downloads / citations if estimable and citations else float("nan")
    mention_ratio = citing_ratio / c if estimable and citations and c == c else float("nan")
    return {
        "tool_id": tool,
        "download_record": download_record,
        "downloads_pypi": downloads_pypi,
        "downloads_github": downloads_github,
        "downloads": downloads,
        "citations": citations,
        "c_measured": c,
        "downloads_per_citing_paper": citing_ratio,
        "downloads_per_mention_or_citation": mention_ratio,
        "estimable": estimable,
        "reason": reason,
    }


def build() -> None:
    """Build pooled and yearly Drake tables offline from the three raw caches."""
    ensure_dirs()
    pypi = _load_cache(PYPI_CACHE)
    github = _load_cache(GITHUB_CACHE)
    openalex = _load_cache(OPENALEX_CACHE)
    c_measured = _citation_measure()
    rows = [_pooled_row(t, pypi, github, openalex, c_measured) for t in ESTIMABLE]
    imagej_citations = _sum_years(
        openalex.get("packages", {}).get("imagej", {}).get("years", {}),
        selected=(2020,),
    )
    imagej_downloads = 500_000
    imagej_c = c_measured.get("imagej", float("nan"))
    imagej_ratio = imagej_downloads / imagej_citations if imagej_citations else float("nan")
    rows.append({
        "tool_id": "imagej",
        "download_record": "reported (image.sc, 2020)",
        "downloads_pypi": 0,
        "downloads_github": 0,
        "downloads": imagej_downloads,
        "citations": imagej_citations,
        "c_measured": imagej_c,
        "downloads_per_citing_paper": imagej_ratio,
        "downloads_per_mention_or_citation": (
            imagej_ratio / imagej_c if imagej_citations and imagej_c == imagej_c
            else float("nan")
        ),
        "estimable": True,
        "reason": "downloads and year from the image.sc discussion",
    })
    rows.extend(_pooled_row(t, pypi, github, openalex, c_measured) for t in NOT_ESTIMABLE)
    pooled = pd.DataFrame(rows, columns=[
        "tool_id", "download_record", "downloads_pypi", "downloads_github", "downloads",
        "citations", "c_measured", "downloads_per_citing_paper",
        "downloads_per_mention_or_citation", "estimable", "reason",
    ])
    pooled.to_csv(POOLED_CSV, index=False)

    yearly_rows = []
    for tool in ("qupath", "cellpose", "stardist"):
        for year in POOLED_YEARS:
            if tool == "qupath":
                downloads = int(github.get("packages", {}).get(tool, {}).get(str(year), 0) or 0)
            else:
                downloads = int(
                    pypi.get("packages", {}).get(tool, {}).get(str(year), {})
                    .get("end_user_installers", 0) or 0
                )
            citations = int(
                openalex.get("packages", {}).get(tool, {}).get("years", {})
                .get(str(year), 0) or 0
            )
            yearly_rows.append({
                "tool_id": tool,
                "year": year,
                "downloads": downloads,
                "citations": citations,
                "downloads_per_citing_paper": downloads / citations if citations else float("nan"),
            })
    pd.DataFrame(yearly_rows, columns=[
        "tool_id", "year", "downloads", "citations", "downloads_per_citing_paper",
    ]).to_csv(YEARLY_CSV, index=False)
    print(f"Wrote {POOLED_CSV}")
    print(f"Wrote {YEARLY_CSV}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build users-and-downloads tables from cached source data.")
    parser.add_argument("--fetch", action="store_true", help="fetch source data before building")
    args = parser.parse_args(argv)
    if args.fetch:
        fetch()
    build()


if __name__ == "__main__":
    main()
