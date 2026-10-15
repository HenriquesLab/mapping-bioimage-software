"""Shared HTTP helpers: polite headers, retries, and an on-disk JSON cache.

The cache makes the whole pipeline reproducible and API-friendly: a second run
reads cached responses instead of repeating live OpenAlex / Europe PMC / GitHub
requests. Cache files live under data/raw/<source>/ keyed by a hash of the URL.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from census._paths import RAW_DIR

# OpenAlex "polite pool" and general contact identification.
CONTACT_EMAIL = "r.henriques@itqb.unl.pt"
USER_AGENT = (
    f"mapping-bioimage-software/2026.10.20 (HenriquesLab; mailto:{CONTACT_EMAIL})"
)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def _cache_path(source: str, url: str, params: dict | None) -> Path:
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    digest = hashlib.sha256(key.encode()).hexdigest()[:20]
    d = RAW_DIR / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{digest}.json"


def get_json(
    source: str,
    url: str,
    params: dict | None = None,
    *,
    use_cache: bool = True,
    max_retries: int = 8,
    pause: float = 0.2,
) -> Any:
    """GET a JSON endpoint with caching + exponential backoff.

    `source` namespaces the cache directory (e.g. "openalex", "europepmc").
    """
    cache = _cache_path(source, url, params)
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = _SESSION.get(url, params=params, timeout=60)
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            resp.raise_for_status()
            data = resp.json()
            cache.write_text(json.dumps(data))
            time.sleep(pause)  # be gentle even on cache misses
            return data
        except (requests.RequestException, ValueError) as exc:  # noqa: PERF203
            last_exc = exc
            time.sleep(min(60, 2 ** (attempt + 1)))
    raise RuntimeError(f"GET failed after {max_retries} tries: {url}") from last_exc
