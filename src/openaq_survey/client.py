"""Client for the OpenAQ v3 API.

Designed to be imported from a notebook: nothing happens at import time, and
the API key is resolved when a request is actually made.

Quick start (in a notebook)
---------------------------
    import openaq_client as oaq
    oaq.set_api_key()               # prompts; the key is never written to disk
    oaq.get("/parameters", {"limit": 100})

Data source
-----------
OpenAQ (https://openaq.org), API v3 at https://api.openaq.org/v3.

Licensing
---------
OpenAQ aggregates from many upstream providers and licence terms differ per
station: each location record carries its own `licenses` array with attribution
requirements. There is no single blanket citation for the whole platform.

Rate limits
-----------
Requests are authenticated with a per-user key in the `X-API-Key` header.
Exceeding the limit returns HTTP 429, with remaining quota and reset time in
the response headers. This module backs off on 429 and self-throttles.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Iterator

import requests

BASE_URL = "https://api.openaq.org/v3"

# Identifies this traffic to the API operator. Replace with your own address.
USER_AGENT = "math70076-assessment-2 (student project; your.name@imperial.ac.uk)"

# Self-imposed minimum gap between calls, in seconds.
MIN_INTERVAL_S = 0.25

_api_key: str | None = None
_last_call = 0.0


# ---------------------------------------------------------------------------
# authentication
# ---------------------------------------------------------------------------

def set_api_key(key: str | None = None) -> None:
    """Set the API key for this session.

    Parameters
    ----------
    key:
        The key itself. If omitted, the environment variable ``OPENAQ_KEY`` is
        used when present; otherwise the user is prompted via ``getpass``, so
        the key is not echoed to the screen and never enters the notebook file.

    Notes
    -----
    Deliberately not read from a config file inside the repository. The
    assessment asks for a public GitHub repo, and a key committed to a public
    repo stays recoverable from git history even after a later commit deletes
    it.
    """
    global _api_key

    if key is not None:
        _api_key = key
        return

    env = os.environ.get("OPENAQ_KEY")
    if env:
        _api_key = env
        print("Key taken from the OPENAQ_KEY environment variable.")
        return

    from getpass import getpass
    _api_key = getpass("Paste your OpenAQ API key (input is hidden): ").strip()
    if not _api_key:
        raise ValueError("no key entered")
    print(f"Key set ({len(_api_key)} characters). Held in memory only.")


def _headers() -> dict:
    if not _api_key:
        raise RuntimeError("No API key set. Run  set_api_key()  first.")
    return {"X-API-Key": _api_key, "User-Agent": USER_AGENT}


# ---------------------------------------------------------------------------
# requests
# ---------------------------------------------------------------------------

def _throttle() -> None:
    global _last_call
    gap = time.monotonic() - _last_call
    if gap < MIN_INTERVAL_S:
        time.sleep(MIN_INTERVAL_S - gap)
    _last_call = time.monotonic()


def get(path: str, params: dict | None = None, max_attempts: int = 5) -> dict:
    """GET one v3 endpoint, retrying on 429 and 5xx with exponential backoff.

    Parameters
    ----------
    path:
        Endpoint path beginning with a slash, e.g. ``"/locations"``.
    params:
        Query parameters.
    max_attempts:
        Total attempts before giving up.

    Returns
    -------
    dict
        Parsed JSON body, with ``meta`` and ``results`` keys.

    Raises
    ------
    RuntimeError
        On a non-retryable 4xx, or after exhausting retries.
    """
    delay = 2.0
    for attempt in range(1, max_attempts + 1):
        _throttle()
        try:
            r = requests.get(f"{BASE_URL}{path}", params=params,
                             headers=_headers(), timeout=90)
        except requests.RequestException as exc:
            if attempt == max_attempts:
                raise RuntimeError(f"network failure on {path}") from exc
            time.sleep(delay)
            delay *= 2
            continue

        if r.status_code == 200:
            return r.json()

        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", delay))
            print(f"  [429] rate limited; sleeping {wait:.0f}s. "
                  f"remaining={r.headers.get('x-ratelimit-remaining')} "
                  f"reset={r.headers.get('x-ratelimit-reset')}")
            time.sleep(wait)
            delay *= 2
            continue

        if r.status_code >= 500 or r.status_code == 408:
            if attempt == max_attempts:
                raise RuntimeError(f"HTTP {r.status_code} on {path}: {r.text[:200]}")
            time.sleep(delay)
            delay *= 2
            continue

        raise RuntimeError(f"HTTP {r.status_code} on {path}: {r.text[:300]}")

    raise RuntimeError(f"gave up on {path}")


def paginate(path: str, params: dict | None = None, page_size: int = 1000,
             max_pages: int | None = None, verbose: bool = True) -> Iterator[dict]:
    """Yield every record from a paginated v3 endpoint.

    Stops when a page returns fewer records than `page_size`, or at `max_pages`.

    Notes
    -----
    Some APIs cap ``page * limit``. If pagination stops well short of
    ``meta.found``, that is the likely cause: split the query by country rather
    than sweeping globally.
    """
    params = dict(params or {})
    params["limit"] = page_size
    page = 1
    total = None

    while True:
        params["page"] = page
        payload = get(path, params)
        if total is None:
            total = payload.get("meta", {}).get("found")
            if verbose:
                print(f"  {path}: meta.found = {total}")

        results = payload.get("results", [])
        if verbose:
            print(f"  page {page}: {len(results)} records")
        yield from results

        if len(results) < page_size:
            return
        page += 1
        if max_pages is not None and page > max_pages:
            if verbose:
                print(f"  stopped at max_pages={max_pages}")
            return


def cached_json(path: str | Path, producer: Callable[[], object]) -> object:
    """Return cached JSON from `path`, or call `producer()` and cache the result.

    Lets the analysis be re-run offline, so the report can be rebuilt without
    hitting the API again. Delete the file to force a refresh.
    """
    path = Path(path)
    if path.exists():
        print(f"  cache hit: {path}")
        return json.loads(path.read_text())
    value = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    print(f"  cached -> {path}")
    return value


# ---------------------------------------------------------------------------
# flattening
# ---------------------------------------------------------------------------

def flatten_stations(records: list[dict]):
    """One row per station, with nested fields lifted out. Returns a DataFrame."""
    import pandas as pd

    rows = []
    for r in records:
        coords = r.get("coordinates") or {}
        country = r.get("country") or {}
        dt_first = r.get("datetimeFirst") or {}
        dt_last = r.get("datetimeLast") or {}
        licences = r.get("licenses") or []
        rows.append({
            "location_id": r.get("id"),
            "name": r.get("name"),
            "locality": r.get("locality"),
            "country_code": country.get("code"),
            "country_name": country.get("name"),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "timezone": r.get("timezone"),
            "provider": (r.get("provider") or {}).get("name"),
            "owner": (r.get("owner") or {}).get("name"),
            "is_monitor": r.get("isMonitor"),
            "is_mobile": r.get("isMobile"),
            "n_sensors": len(r.get("sensors") or []),
            "instrument": (r.get("instruments") or [{}])[0].get("name"),
            "n_instruments": len(r.get("instruments") or []),
            "datetime_first": dt_first.get("utc") if isinstance(dt_first, dict) else None,
            "datetime_last": dt_last.get("utc") if isinstance(dt_last, dict) else None,
            "licence": licences[0].get("name") if licences else None,
            "licence_from": licences[0].get("dateFrom") if licences else None,
            "attribution": (licences[0].get("attribution") or {}).get("name") if licences else None,
        })
    return pd.DataFrame(rows)


def flatten_sensors(records: list[dict]):
    """One row per sensor: which station measures which pollutant. Returns a DataFrame."""
    import pandas as pd

    rows = []
    for r in records:
        for s in r.get("sensors") or []:
            p = s.get("parameter") or {}
            rows.append({
                "sensor_id": s.get("id"),
                "location_id": r.get("id"),
                "country_code": (r.get("country") or {}).get("code"),
                "parameter_id": p.get("id"),
                "parameter": p.get("name"),
                "units": p.get("units"),
                "is_monitor": r.get("isMonitor"),
            })
    return pd.DataFrame(rows)
