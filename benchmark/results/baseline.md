# ShopLite load test: baseline

1,000 requests per run, median of 3 runs. Recorded 2026-10-24T01:44:40+00:00 on commit `e83cb07`.

| Endpoint | Requests | Queries/request | Avg server ms | Total queries |
| --- | ---: | ---: | ---: | ---: |
| `/users/summary` | 334 | 201.0 | 7.6 | 67,134 |
| `/products/report` | 333 | 1.0 | 105.9 | 333 |
| `/users/<id>` | 333 | 2.0 | 0.4 | 666 |

| Metric | Value |
| --- | ---: |
| Total runtime | 38.50 s |
| Server CPU time | 37.61 s |
| Total DB queries | 68,207 |
| ...from requests | 68,133 |
| ...from background work | 74 |
| Idle DB queries (10 s, no requests) | 20 |
| Idle server CPU time | 0.015 s |
| Failed requests | 0 |
| Estimated energy, load phase | 0.137 Wh |
| Estimated CO₂, load phase (california, USA grid) | 0.024 g |

Runtime and CPU time are proxies for energy use; query counts are exact.
Energy and CO₂ are estimates from codecarbon 3.3.2 in offline mode: CPU load × typical power of the Apple M4, plus RAM, for the whole machine, not only ShopLite.

Environment: Python 3.9.6 on macOS-26.5.1-arm64-arm-64bit (10 CPUs).
