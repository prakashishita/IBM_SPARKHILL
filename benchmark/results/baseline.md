# ShopLite load test: baseline

1,000 requests per run, median of 3 runs. Recorded 2026-10-24T01:30:01+00:00 on commit `3c42205`.

| Endpoint | Requests | Queries/request | Avg server ms | Total queries |
| --- | ---: | ---: | ---: | ---: |
| `/users/summary` | 334 | 201.0 | 7.0 | 67,134 |
| `/products/report` | 333 | 1.0 | 104.2 | 333 |
| `/users/<id>` | 333 | 2.0 | 0.3 | 666 |

| Metric | Value |
| --- | ---: |
| Total runtime | 37.71 s |
| Server CPU time | 37.23 s |
| Total DB queries | 68,205 |
| ...from requests | 68,133 |
| ...from background work | 72 |
| Idle DB queries (10 s, no requests) | 20 |
| Idle server CPU time | 0.010 s |
| Failed requests | 0 |

Runtime and CPU time are proxies for energy use; query counts are exact.

Environment: Python 3.9.6 on macOS-26.5.1-arm64-arm-64bit (10 CPUs).
