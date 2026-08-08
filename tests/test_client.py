"""Tests for the OpenAQ client.

These run without network access: the HTTP layer is stubbed out. That is
deliberate. A test suite that needs a live API and a valid key is a test suite
nobody else can run, which defeats the point of shipping tests at all.

Run with:  pytest
"""

import pytest

from openaq_survey import client


def test_headers_raise_without_key(monkeypatch):
    """Calling the API without a key should fail loudly, not silently 401."""
    monkeypatch.setattr(client, "_api_key", None)
    with pytest.raises(RuntimeError, match="No API key"):
        client._headers()


def test_set_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENAQ_KEY", "test-key-123")
    monkeypatch.setattr(client, "_api_key", None)
    client.set_api_key()
    assert client._api_key == "test-key-123"


def test_flatten_stations_handles_missing_nested_fields():
    """A record with every optional field absent must not raise.

    Real API responses are inconsistent: some stations have no owner, no
    licence, or no coordinates. Flattening should degrade to None rather than
    throw a KeyError halfway through a 20-minute fetch.
    """
    records = [{"id": 1, "name": "bare"}]
    df = client.flatten_stations(records)
    assert len(df) == 1
    assert df.loc[0, "location_id"] == 1
    assert df.loc[0, "country_code"] is None
    assert df.loc[0, "n_sensors"] == 0


def test_flatten_sensors_expands_one_row_per_sensor():
    records = [{
        "id": 7,
        "country": {"code": "JP"},
        "sensors": [
            {"id": 100, "parameter": {"id": 2, "name": "pm25", "units": "ug/m3"}},
            {"id": 101, "parameter": {"id": 5, "name": "no2", "units": "ppm"}},
        ],
    }]
    df = client.flatten_sensors(records)
    assert len(df) == 2
    assert set(df["parameter"]) == {"pm25", "no2"}
    assert (df["location_id"] == 7).all()


def test_paginate_stops_on_short_page(monkeypatch):
    """Pagination must stop when a page returns fewer records than requested."""
    pages = {
        1: {"meta": {"found": 3}, "results": [{"id": 1}, {"id": 2}]},
        2: {"meta": {"found": 3}, "results": [{"id": 3}]},
    }
    monkeypatch.setattr(client, "get", lambda path, params: pages[params["page"]])
    out = list(client.paginate("/locations", page_size=2, verbose=False))
    assert [r["id"] for r in out] == [1, 2, 3]


def test_paginate_respects_max_pages(monkeypatch):
    """A runaway sweep must be stoppable, so exploratory calls stay cheap."""
    monkeypatch.setattr(
        client, "get",
        lambda path, params: {"meta": {"found": 999}, "results": [{"id": 1}, {"id": 2}]},
    )
    out = list(client.paginate("/locations", page_size=2, max_pages=3, verbose=False))
    assert len(out) == 6


def test_cached_json_roundtrip(tmp_path):
    """Second call must read the cache and not invoke the producer again."""
    calls = []

    def producer():
        calls.append(1)
        return {"a": 1}

    path = tmp_path / "cache.json"
    first = client.cached_json(path, producer)
    second = client.cached_json(path, producer)

    assert first == second == {"a": 1}
    assert len(calls) == 1, "producer was called twice; cache did not work"
