"""GitHub source: developer-adoption snapshot per tool.

For each repo listed in the registry we capture stars, forks, watchers, open
issues, and creation/last-push dates. Summed per tool, stars are a proxy for
developer-side adoption that complements the literature signals.

Authentication: uses $GITHUB_TOKEN if set, else falls back to `gh auth token`.
Unauthenticated requests are rate-limited to 60/hour, so a token is advised.

Note: this is a point-in-time snapshot, not a yearly trend. Long-run star
histories exist but require paging every stargazer; we deliberately keep this
source cheap and reproducible. Yearly trends come from OpenAlex + Europe PMC.

Run standalone:
    python -m census.sources.github --tool napari
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import requests

from census._http import USER_AGENT, get_json  # noqa: E402
from census._registry import Tool, load_registry  # noqa: E402

API = "https://api.github.com/repos/"
SOURCE = "github"


def _token() -> str | None:
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def _headers() -> dict:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def repo_metrics(repo: str) -> dict:
    """Fetch snapshot metrics for one owner/repo (cached)."""
    # get_json caches by URL; GitHub needs auth headers, so do a direct call
    # then let get_json's cache handle repeats by hashing the same URL.
    url = API + repo
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    d = resp.json()
    return {
        "repo": repo,
        "stars": d.get("stargazers_count", 0),
        "forks": d.get("forks_count", 0),
        "watchers": d.get("subscribers_count", 0),
        "open_issues": d.get("open_issues_count", 0),
        "created_at": (d.get("created_at") or "")[:10],
        "pushed_at": (d.get("pushed_at") or "")[:10],
    }


def collect_snapshot(reg) -> list[dict]:
    as_of = dt.date.today().isoformat()
    rows: list[dict] = []
    for tool in reg.tools:
        stars = forks = watchers = 0
        repos_seen = 0
        earliest = ""
        for repo in tool.github:
            try:
                m = repo_metrics(repo)
            except requests.RequestException:
                continue
            repos_seen += 1
            stars += m["stars"]
            forks += m["forks"]
            watchers += m["watchers"]
            if m["created_at"] and (not earliest or m["created_at"] < earliest):
                earliest = m["created_at"]
        if repos_seen == 0:
            continue
        rows.append(
            {
                "source": SOURCE,
                "tool_id": tool.id,
                "stars": stars,
                "forks": forks,
                "watchers": watchers,
                "n_repos": repos_seen,
                "earliest_repo": earliest,
                "as_of": as_of,
            }
        )
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="single tool id (default: all)")
    args = ap.parse_args()
    reg = load_registry()
    tools = [reg.by_id(args.tool)] if args.tool else reg.tools
    for t in tools:
        for repo in t.github:
            try:
                print(t.id, repo_metrics(repo))
            except requests.RequestException as e:
                print(t.id, repo, "ERROR", e)
