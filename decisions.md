# Decision log — math70076 assessment 2 (OpenAQ coverage analysis)

One entry per consequential decision, with the reason recorded at the time.
Rule adopted mid-project: anything proposed by an AI assistant counts as a
candidate, not a decision — it enters this log only after being re-derived
or verified against the actual data/API. Dates from git history where the
decision left a commit; approximate otherwise.

| # | Date (2026) | Decision | Reason |
|---|------|----------|--------|
| 1 | __-__ | Project question fixed as: does OpenAQ's coverage reproduce the inequality it exists to correct? | Needs to carry an argument (Q2), not just a description. |
| 2 | __-__ | Source selection criteria written down *before* comparing candidates: (a) real acquisition friction, (b) can support an argument, (c) enough computation to profile later. | Prevents relitigating scope on every new idea; later used to reject scope creep (second pollutant, time dimension). |
| 3 | __-__ | ENTSO-E rejected despite richer data. | Token issued in 3 working days; incompatible with deadline. Criteria applied, not preference. |
| 4 | __-__ | OpenAQ v3 selected. | Meets all three criteria: auth + rate limits + pagination; coverage question; 25k+ stations to compute over. |
| 5 | __-__ | World Bank Indicators API added for population and PM2.5. | Station counts meaningless without denominators (442 stations means different things in Pakistan vs Finland). |
| 6 | __-__ | API key moved to `.env`, key rotated. | Key was pasted into an AI chat during debugging. Reactive fix; lesson logged: secrets location is a first-hour decision. |
| 7 | __-__ | All API responses cached to disk. | Politeness to a rate-limited API; later enabled full offline re-run after kernel death. |
| 8 | __-__ | Aggregation switched to server-side `/days` endpoints. | Raw-measurement aggregation returned 408 timeouts. |
| 9 | __-__ | Code packaged as installable (`pip install -e .`), src layout. | Imports identical on any machine; no `sys.path` hacks. |
| 10 | __-__ | Test suite must run offline with no credentials. | A test only the author can run is documentation, not a check. |
| 11 | __-__ | Figure: scatter + log axis rejected; diverging bar chart chosen. | Strongest evidence is the zeros; zero cannot sit on a log axis, but a missing bar is visible by construction. |
| 12 | __-__ | Figure audience fixed: programme officer at a funder/agency. | Fixed late (after first draft of the figure) — logged as a sequencing mistake. All figure decisions re-checked against this reader. |
| 13 | __-__ | Selection tie-break: PM2.5 first, population second. | Where exposure is equal, the country with more affected people matters more to this audience. |
| 14 | __-__ | Zero-value rows get a coloured origin dot + text annotation. | First render showed zero-length bars are invisible, deleting the colour channel for exactly the countries that matter. |
| 15 | __-__ | Figure caveat placed inside the figure, not in surrounding text. | The intended reader will not read a methods section. Zero on OpenAQ ≠ no national monitoring. |
| 16 | __-__ | Distance function: pure NumPy; geopy / sklearn BallTree rejected. | Portability over elegance; no heavyweight dependency for a computation that takes seconds. |
| 17 | __-__ | Naive double-loop implementation kept in the module permanently. | Serves as correctness oracle for tests and "before" case for profiling. Deliberate maintainability expense. |
| 18 | __-__ | Chunked broadcasting with `chunk_size` exposed; default 2000. | Full 141M-pair matrix ≈ 1.1 GB per intermediate array. |
| 19 | __-__ | Docstring claim "larger chunks are faster" corrected after profiling. | Chunk sweep falsified it: 200/block fastest (2.46 s, ~27 MB); whole dataset in one block slowest (4.97 s, ~1.1 GB). Cache/bandwidth-bound. |
| 20 | __-__ | Further optimisation (BallTree tier) declined. | Function no longer the pipeline's slowest step; dependency + loss of line-by-line testability not worth seconds. |
| 21 | __-__ | Report question 5 anchored on this solo project rather than the group data challenge. | Brief permits any experience; reproducibility evidence is strongest here; collaboration addressed honestly via managing the AI assistant. |
