"""Compare two load-test results and report the change.

Usage: python compare.py                          (results/baseline.json vs results/after.json)
       python compare.py results/a.json results/b.json
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

METRICS = [
    ("Total runtime", "runtime_s", "{:.2f} s"),
    ("Server CPU time", "server_cpu_s", "{:.2f} s"),
    ("Total DB queries", "total_queries", "{:,.0f}"),
    ("Idle DB queries", "idle_queries", "{:,.0f}"),
    ("Idle server CPU time", "idle_cpu_s", "{:.3f} s"),
    ("Estimated energy (load phase)", "energy_wh", "{:.3f} Wh"),
    ("Estimated CO₂ (load phase)", "co2_g", "{:.3f} g"),
]


def change(before, after):
    if before == 0:
        return "–" if after == 0 else "new"
    return f"{(after - before) / before * 100:+.1f}%"


def main():
    paths = [Path(p) for p in sys.argv[1:3]] or [HERE / "results" / "baseline.json", HERE / "results" / "after.json"]
    before, after = (json.loads(p.read_text()) for p in paths)
    b, a = before["summary"], after["summary"]

    lines = [
        f"# ShopLite: {before['label']} vs {after['label']}",
        "",
        f"Commits `{before['environment']['git']['commit']}` → `{after['environment']['git']['commit']}`, "
        f"{after['config']['requests']:,} requests, median of {after['config']['runs']} runs.",
        "",
        f"| Metric | {before['label']} | {after['label']} | Change |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, key, fmt in METRICS:
        if key not in b or key not in a:
            continue
        lines.append(f"| {name} | {fmt.format(b[key])} | {fmt.format(a[key])} | {change(b[key], a[key])} |")

    lines += [
        "",
        f"| Endpoint | Queries/request | Avg server ms |",
        "| --- | ---: | ---: |",
    ]
    for e in b["endpoints"]:
        be, ae = b["endpoints"][e], a["endpoints"][e]
        lines.append(f"| `{e}` | {be['queries_per_request']:,.1f} → {ae['queries_per_request']:,.1f} | "
                     f"{be['avg_server_ms']:,.1f} → {ae['avg_server_ms']:,.1f} |")

    lines += ["", "Runtime and CPU time are proxies for energy use; query counts are exact."]
    if "energy_wh" in b and "energy_wh" in a:
        lines.append("Energy and CO₂ are codecarbon estimates for the whole machine, not measured values.")
    lines.append("")
    if a["errors"]:
        lines.insert(2, f"**Warning: {a['errors']} failed requests in '{after['label']}'.**\n")

    out = HERE / "results" / "comparison.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
