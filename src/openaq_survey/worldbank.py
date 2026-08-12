"""Client for the World Bank Indicators API.

Provides the denominators the OpenAQ station counts need: population, modelled
PM2.5 exposure, and the World Bank income classification.

Contrast with the OpenAQ client
-------------------------------
Worth noting when comparing the two APIs, since they made opposite choices:

  - No authentication. No key, no registration, no per-user rate limit.
  - Pagination metadata is a real integer (`total`), not the `">1000"` string
    OpenAQ returns, so the number of pages is knowable in advance.
  - The response is a two-element array `[metadata, data]` rather than an
    object with named keys, which is a less self-describing design.
  - Missing values are returned as JSON null inside otherwise complete records,
    rather than the `-99` sentinel that appears in the OpenAQ country codes.

Licensing
---------
World Bank open data are published under CC BY 4.0. Attribution is required.

Indicator provenance -- read before drawing conclusions
-------------------------------------------------------
`EN.ATM.PM25.MC.M3` is *modelled* population-weighted PM2.5 exposure, produced
by combining satellite retrievals, chemical transport models and ground
measurements. It is not a measurement. This matters here: ground measurement
density is one of its inputs, so countries with few monitors have more
uncertain exposure estimates. Using it as an independent axis against
monitoring density is therefore not fully independent -- state this limitation
rather than ignoring it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

import requests

BASE_URL = "https://api.worldbank.org/v2"
USER_AGENT = "math70076-assessment-2 (student project; your.name@imperial.ac.uk)"

# Indicator codes used here.
POPULATION = "SP.POP.TOTL"
PM25_EXPOSURE = "EN.ATM.PM25.MC.M3"
GNI_PER_CAPITA = "NY.GNP.PCAP.CD"

MIN_INTERVAL_S = 0.3
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    gap = time.monotonic() - _last_call
    if gap < MIN_INTERVAL_S:
        time.sleep(MIN_INTERVAL_S - gap)
    _last_call = time.monotonic()


def _get(path: str, params: dict | None = None, max_attempts: int = 4) -> list:
    """GET a World Bank endpoint and return the parsed JSON array."""
    params = dict(params or {})
    params["format"] = "json"
    delay = 2.0

    for attempt in range(1, max_attempts + 1):
        _throttle()
        try:
            r = requests.get(f"{BASE_URL}{path}", params=params,
                             headers={"User-Agent": USER_AGENT}, timeout=60)
        except requests.RequestException as exc:
            if attempt == max_attempts:
                raise RuntimeError(f"network failure on {path}") from exc
            time.sleep(delay)
            delay *= 2
            continue

        if r.status_code == 200:
            payload = r.json()
            # The API signals errors with HTTP 200 and a message body, so the
            # status code alone is not enough to tell success from failure.
            if isinstance(payload, list) and payload and "message" in (payload[0] or {}):
                raise RuntimeError(f"API error on {path}: {payload[0]['message']}")
            return payload

        if r.status_code >= 500:
            if attempt == max_attempts:
                raise RuntimeError(f"HTTP {r.status_code} on {path}")
            time.sleep(delay)
            delay *= 2
            continue

        raise RuntimeError(f"HTTP {r.status_code} on {path}: {r.text[:200]}")

    raise RuntimeError(f"gave up on {path}")


def fetch_countries():
    """Return one row per World Bank country entity.

    Returns
    -------
    pandas.DataFrame
        Columns: iso2, iso3, country_name, region, income_group, is_aggregate.

    Notes
    -----
    The endpoint mixes real countries with aggregates such as "World" and
    "Sub-Saharan Africa". Aggregates have region id ``NA``; the
    ``is_aggregate`` column flags them so they can be dropped before any
    per-country analysis. Failing to drop them double-counts badly.
    """
    import pandas as pd

    payload = _get("/country", {"per_page": 400})
    rows = []
    for c in payload[1]:
        region = (c.get("region") or {}).get("value")
        rows.append({
            "iso2": c.get("iso2Code"),
            "iso3": c.get("id"),
            "country_name": c.get("name"),
            "region": region,
            "income_group": (c.get("incomeLevel") or {}).get("value"),
            "is_aggregate": region == "Aggregates",
        })
    return pd.DataFrame(rows)


def fetch_indicator(indicator: str, mrv: int = 5):
    """Fetch the most recent values of one indicator for every country.

    Parameters
    ----------
    indicator:
        World Bank indicator code, e.g. ``"SP.POP.TOTL"``.
    mrv:
        Most Recent Values: how many recent years to request per country.
        More than one is requested because the latest year is often null for
        many countries; take the newest non-null per country downstream.

    Returns
    -------
    pandas.DataFrame
        Columns: iso3, iso2, year, value, indicator.
    """
    import pandas as pd

    payload = _get(f"/country/all/indicator/{indicator}",
                   {"per_page": 20000, "mrv": mrv})
    total = payload[0].get("total")
    print(f"  {indicator}: {total} records reported")

    rows = []
    for rec in payload[1] or []:
        rows.append({
            "iso3": (rec.get("countryiso3code") or None),
            "iso2": (rec.get("country") or {}).get("id"),
            "year": int(rec["date"]) if rec.get("date") else None,
            "value": rec.get("value"),
            "indicator": indicator,
        })
    return pd.DataFrame(rows)


def latest_non_null(df):
    """Collapse a multi-year indicator frame to the newest non-null per country."""
    return (
        df.dropna(subset=["value", "iso3"])
          .sort_values("year")
          .groupby("iso3", as_index=False)
          .last()
    )


def cached_json(path: str | Path, producer: Callable[[], object]) -> object:
    """Return cached JSON from `path`, or call `producer()` and cache the result."""
    path = Path(path)
    if path.exists():
        print(f"  cache hit: {path}")
        return json.loads(path.read_text())
    value = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    print(f"  cached -> {path}")
    return value