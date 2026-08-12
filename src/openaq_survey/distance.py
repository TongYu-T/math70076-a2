"""Great-circle distances between monitoring stations.

Used to measure, for every low-cost sensor in the OpenAQ inventory, the
distance to the nearest reference-grade monitor. All functions take
coordinates in decimal degrees and return distances in kilometres; no
projected CRS or external geospatial dependency is required.
"""

from __future__ import annotations

import numpy as np

#: Mean Earth radius in kilometres (IUGG value).
EARTH_RADIUS_KM = 6371.0088


def _validate_coords(lat: np.ndarray, lon: np.ndarray, name: str) -> None:
    """Raise ValueError with a specific message if coordinates are unusable."""
    if lat.shape != lon.shape:
        raise ValueError(
            f"{name}: latitude and longitude have different shapes "
            f"({lat.shape} vs {lon.shape})"
        )
    if lat.size == 0:
        raise ValueError(f"{name}: coordinate arrays are empty")
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        n_bad = int((~np.isfinite(lat) | ~np.isfinite(lon)).sum())
        raise ValueError(
            f"{name}: {n_bad} non-finite coordinate(s); drop or impute "
            "missing positions before calling"
        )
    if (np.abs(lat) > 90).any():
        raise ValueError(f"{name}: latitude outside [-90, 90] — are lat/lon swapped?")
    if (np.abs(lon) > 180).any():
        raise ValueError(f"{name}: longitude outside [-180, 180]")


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between points on Earth, in kilometres.

    Inputs are decimal degrees and may be scalars or arrays; NumPy
    broadcasting rules apply, so a column vector against a row vector
    yields a full distance matrix.

    Parameters
    ----------
    lat1, lon1 : float or ndarray
        Coordinates of the first point(s), decimal degrees.
    lat2, lon2 : float or ndarray
        Coordinates of the second point(s), decimal degrees.

    Returns
    -------
    float or ndarray
        Distance(s) in kilometres.

    Examples
    --------
    >>> round(haversine_km(51.5074, -0.1278, 48.8575, 2.3514), 1)  # London-Paris
    343.9
    """
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def nearest_reference_km(
    query_lat,
    query_lon,
    ref_lat,
    ref_lon,
    chunk_size: int = 2000,
):
    """Distance from each query point to its nearest reference point, in km.

    For every point in ``(query_lat, query_lon)`` — e.g. low-cost sensors —
    compute the great-circle distance to the closest point in
    ``(ref_lat, ref_lon)`` — e.g. reference-grade monitors.

    The full pairwise distance matrix for the OpenAQ inventory
    (~8,000 x ~17,000 points) does not fit comfortably in memory, so the
    computation is chunked: ``chunk_size`` query points are broadcast
    against all reference points at a time. Peak memory scales as
    ``chunk_size * n_ref * 8`` bytes per intermediate array, but speed
    does not improve monotonically with chunk size: profiling on the full
    inventory showed a few hundred rows per block is fastest, and very
    large blocks are slower (cache- and bandwidth-bound; see report
    Appendix D). The default is a reasonable middle setting.

    Parameters
    ----------
    query_lat, query_lon : array-like
        Coordinates of the query points, decimal degrees.
    ref_lat, ref_lon : array-like
        Coordinates of the reference points, decimal degrees. Must be
        non-empty.
    chunk_size : int, optional
        Number of query points processed per block. Affects speed and
        memory only, never the result.

    Returns
    -------
    ndarray
        1-D array, same length as the query arrays: distance in km from
        each query point to its nearest reference point.

    Raises
    ------
    ValueError
        If any coordinate array is empty, contains non-finite values, or
        lies outside valid latitude/longitude ranges.
    """
    query_lat = np.asarray(query_lat, dtype=float).ravel()
    query_lon = np.asarray(query_lon, dtype=float).ravel()
    ref_lat = np.asarray(ref_lat, dtype=float).ravel()
    ref_lon = np.asarray(ref_lon, dtype=float).ravel()
    _validate_coords(query_lat, query_lon, "query")
    _validate_coords(ref_lat, ref_lon, "reference")

    out = np.empty(query_lat.size, dtype=float)
    for start in range(0, query_lat.size, chunk_size):
        stop = start + chunk_size
        block = haversine_km(
            query_lat[start:stop, None],
            query_lon[start:stop, None],
            ref_lat[None, :],
            ref_lon[None, :],
        )
        out[start:stop] = block.min(axis=1)
    return out


def nearest_reference_km_naive(query_lat, query_lon, ref_lat, ref_lon):
    """Reference implementation of :func:`nearest_reference_km`.

    Plain double loop over Python floats. Orders of magnitude slower, but
    obviously correct — kept as the oracle the fast implementation is
    tested against, and as the "before" case for profiling.
    """
    query_lat = np.asarray(query_lat, dtype=float).ravel()
    query_lon = np.asarray(query_lon, dtype=float).ravel()
    ref_lat = np.asarray(ref_lat, dtype=float).ravel()
    ref_lon = np.asarray(ref_lon, dtype=float).ravel()
    _validate_coords(query_lat, query_lon, "query")
    _validate_coords(ref_lat, ref_lon, "reference")

    out = np.empty(query_lat.size, dtype=float)
    for i in range(query_lat.size):
        best = np.inf
        for j in range(ref_lat.size):
            d = haversine_km(query_lat[i], query_lon[i], ref_lat[j], ref_lon[j])
            if d < best:
                best = d
        out[i] = best
    return out