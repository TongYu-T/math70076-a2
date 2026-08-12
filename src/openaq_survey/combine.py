"""Combine OpenAQ station counts with World Bank country-level denominators.

The joins here are mechanical. The decisions are not, and they are exposed as
explicit arguments rather than buried in the code:

  - which countries to drop, and why (`drop_codes`)
  - whether "coverage" means all stations or reference-grade only
  - what to do with countries that appear in one source but not the other

`diagnose_join` prints both directions of failure. Read it before using the
merged table: silently dropping the countries that fail to match is the fastest
way to produce a confident and wrong answer about global coverage.
"""

from __future__ import annotations

import pandas as pd

# ISO2 values that are not countries. "-99" is a missing-value sentinel that
# appears in the OpenAQ country codes; treating it as a country would create a
# phantom row in every aggregation.
SENTINEL_CODES = ("-99",)


def prepare_worldbank(countries: pd.DataFrame,
                      indicators: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Assemble one row per country from the World Bank country list and indicators.

    Parameters
    ----------
    countries:
        Output of ``worldbank.fetch_countries()``.
    indicators:
        Mapping of output column name to the frame returned by
        ``worldbank.latest_non_null(...)``, e.g.
        ``{"population": pop, "pm25": pm25, "gni_per_capita": gni}``.

    Returns
    -------
    pandas.DataFrame
        Countries only (aggregates removed), one row per ISO3, with one column
        per indicator plus a ``<name>_year`` column recording which year each
        value came from.

    Notes
    -----
    Aggregate entities such as "World" and "Sub-Saharan Africa" are removed
    here. They share the same schema as real countries, so leaving them in
    would double-count every region.

    Indicator years are kept because ``latest_non_null`` takes the most recent
    non-null value per country, which is not the same year for every country.
    A reader comparing two countries deserves to know if one figure is from
    2024 and the other from 2019.
    """
    out = countries.loc[~countries["is_aggregate"]].copy()
    dropped = len(countries) - len(out)
    print(f"prepare_worldbank: dropped {dropped} aggregate entities, "
          f"{len(out)} countries remain")

    for name, frame in indicators.items():
        slim = frame[["iso3", "value", "year"]].rename(
            columns={"value": name, "year": f"{name}_year"}
        )
        out = out.merge(slim, on="iso3", how="left")
        n_missing = out[name].isna().sum()
        print(f"  {name:<16} missing for {n_missing:>3} of {len(out)} countries")

    return out


def diagnose_join(stations_by_country: pd.DataFrame,
                  wb: pd.DataFrame,
                  left_key: str = "country_code",
                  right_key: str = "iso2") -> dict[str, pd.DataFrame]:
    """Report which countries fail to match, in both directions.

    Returns
    -------
    dict
        ``"openaq_only"``  -- has stations but no World Bank record
        ``"worldbank_only"`` -- a country with no stations at all

    Notes
    -----
    The second group is substantive, not an error. A country present in the
    World Bank list and absent from OpenAQ has zero stations on the platform.
    Dropping those rows with an inner join would remove exactly the cases that
    matter most to any claim about coverage gaps.
    """
    left = set(stations_by_country[left_key].dropna())
    right = set(wb[right_key].dropna())

    openaq_only = stations_by_country[
        stations_by_country[left_key].isin(left - right)
    ].sort_values("n_stations", ascending=False)

    worldbank_only = wb[wb[right_key].isin(right - left)].copy()

    print(f"\ndiagnose_join:")
    print(f"  matched                       : {len(left & right)}")
    print(f"  in OpenAQ but not World Bank  : {len(openaq_only)}")
    if len(openaq_only):
        print("    " + ", ".join(
            f"{r[left_key]}({r['n_stations']})"
            for _, r in openaq_only.head(15).iterrows()
        ))
    print(f"  in World Bank but not OpenAQ  : {len(worldbank_only)}")
    if len(worldbank_only) and "population" in worldbank_only:
        pop = worldbank_only["population"].sum()
        print(f"    combined population of countries with zero stations: "
              f"{pop:,.0f}")

    return {"openaq_only": openaq_only, "worldbank_only": worldbank_only}


def build_country_table(stations_by_country: pd.DataFrame,
                        wb: pd.DataFrame,
                        drop_codes: tuple[str, ...] = SENTINEL_CODES,
                        keep_unmatched_worldbank: bool = True) -> pd.DataFrame:
    """Join station counts to country denominators and derive coverage rates.

    Parameters
    ----------
    stations_by_country:
        One row per ISO2 country code with ``n_stations``, ``n_reference``,
        ``n_sensors``, ``earliest``.
    wb:
        Output of :func:`prepare_worldbank`.
    drop_codes:
        ISO2 values to remove from the OpenAQ side before joining. Defaults to
        the ``-99`` sentinel. Anything else dropped here is a judgement you are
        making about the analysis and should be justified in writing.
    keep_unmatched_worldbank:
        If True (the default) countries with no OpenAQ presence are kept with
        zero station counts. Set False only if you can justify excluding them.

    Returns
    -------
    pandas.DataFrame
        One row per country with raw counts, per-capita rates and the
        reference-grade share.

    Notes
    -----
    Rates are per million inhabitants. ``ref_share`` is the fraction of a
    country's stations that OpenAQ flags as reference monitors -- see the
    caveat in the project README about how far that flag can be trusted.
    """
    left = stations_by_country.loc[
        ~stations_by_country["country_code"].isin(drop_codes)
    ].copy()
    n_dropped = len(stations_by_country) - len(left)
    if n_dropped:
        print(f"build_country_table: dropped {n_dropped} row(s) "
              f"with codes {drop_codes}")

    how = "outer" if keep_unmatched_worldbank else "inner"
    merged = wb.merge(
        left.drop(columns=[c for c in ("country_name",) if c in left]),
        left_on="iso2", right_on="country_code", how=how,
    )

    # Countries present only in the World Bank list genuinely have no stations.
    for col in ("n_stations", "n_reference", "n_sensors"):
        if col in merged:
            merged[col] = merged[col].fillna(0).astype(int)

    per_million = merged["population"] / 1e6
    merged["stations_per_million"] = merged["n_stations"] / per_million
    merged["reference_per_million"] = merged["n_reference"] / per_million
    merged["ref_share"] = (
        merged["n_reference"] / merged["n_stations"].replace(0, pd.NA)
    )

    print(f"build_country_table: {len(merged)} rows, "
          f"{(merged['n_stations'] == 0).sum()} with zero stations")
    return merged


# ---------------------------------------------------------------------------
# DECISIONS YOU STILL HAVE TO MAKE -- do not leave these to the defaults
# ---------------------------------------------------------------------------
#
# 1. Taiwan (TW, 126 stations) has no World Bank country record. Dropping it,
#    keeping it with a missing denominator, or substituting population from
#    another source are all defensible; which you choose, and the fact that the
#    choice exists at all, belongs in the write-up. Data frameworks encode
#    political judgements, and this is a concrete instance rather than an
#    abstract worry.
#
# 2. Coverage measured by `n_stations` or by `n_reference`? These give
#    materially different rankings -- Pakistan is 13th by the first measure and
#    near the bottom by the second. Whichever you pick, say why, and show the
#    other one somewhere.
#
# 3. `earliest` varies enormously (Japan's platform record starts in 2023).
#    A country can look absent because it is not monitored, or because its
#    national network has not been ingested by OpenAQ. These are different
#    claims. Decide which one your figure is actually making.
#
# 4. `population` and `pm25` come from different years for different countries.
#    Check the `*_year` columns before comparing.