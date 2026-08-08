# Who gets measured? Coverage of the OpenAQ monitoring network

Supporting code for MATH70076 Data Science, Assessment 2 (Imperial College London).

## Data source and attribution

Air quality station metadata from the [OpenAQ](https://openaq.org) API v3.

OpenAQ aggregates from many upstream providers and **licence terms differ per
station**: each location record carries its own `licenses` array with its own
attribution requirement. There is no single blanket citation for the platform.

## Reproducing

```bash
git clone <your-repo-url>
cd math70076-a2
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                          # runs offline, no API key needed

export OPENAQ_KEY="your-key"    # free, from explore.openaq.org/account
jupyter lab notebooks/          # or open the folder in VS Code
```

API responses are cached under `data/`, so the analysis reruns offline after
the first fetch.

## Layout

```
src/openaq_survey/client.py   acquisition: auth, pagination, retry, caching
notebooks/01_acquire.ipynb    narrative: calls the module, inspects results
tests/test_client.py          offline test suite
data/                         cached responses and derived tables (gitignored)
```

## Acknowledgements

<!-- TODO complete honestly before submitting: state which parts were written
     with AI assistance and which are your own. The assessment asks you to
     reflect on this rather than conceal it. -->
