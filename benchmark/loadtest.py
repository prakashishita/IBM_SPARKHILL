"""Load-test ShopLite and record runtime, server CPU time and DB queries.

The script owns the whole run: it seeds a private copy of the database,
starts the ShopLite server, sends the workload, measures an idle window,
then stops the server. Every run starts from the same state, so the
"before" and "after" numbers are comparable.

Usage:
    python loadtest.py --label baseline     # before Bob's fixes
    python loadtest.py --label after        # after Bob's fixes
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
DEFAULT_APP_DIR = HERE.parent / "shoplite"

# Endpoints in the workload, sent round-robin. /users/<id> is a control:
# it is already efficient and should not change between before and after.
ENDPOINTS = ["/users/summary", "/products/report", "/users/<id>"]
NUM_USERS = 200


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", default="baseline", help="name of this measurement (default: baseline)")
    p.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DIR, help="ShopLite folder")
    p.add_argument("--python", help="Python used to run ShopLite (default: <app-dir>/.venv/bin/python)")
    p.add_argument("--requests", type=int, default=1000, help="requests per run (default: 1000)")
    p.add_argument("--runs", type=int, default=3, help="runs; the median is reported (default: 3)")
    p.add_argument("--idle", type=float, default=10, help="idle window in seconds (default: 10)")
    p.add_argument("--port", type=int, default=5077)
    p.add_argument("--out-dir", type=Path, default=HERE / "results")
    return p.parse_args()


def get_json(base, path, method="GET"):
    req = urllib.request.Request(base + path, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def wait_until_up(base, proc, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            sys.exit("ShopLite exited during startup. Run it by hand to see the error.")
        try:
            get_json(base, "/api")
            return
        except OSError:
            time.sleep(0.2)
    sys.exit(f"ShopLite did not start within {timeout} s.")


def cpu_seconds(proc):
    t = proc.cpu_times()
    return t.user + t.system


def workload(n):
    for i in range(n):
        endpoint = ENDPOINTS[i % len(ENDPOINTS)]
        if endpoint == "/users/<id>":
            yield endpoint, f"/users/{(i // len(ENDPOINTS)) % NUM_USERS + 1}"
        else:
            yield endpoint, endpoint


def run_once(args, python, run_no):
    db_file = Path(tempfile.mkdtemp(prefix="shoplite-bench-")) / "app.db"
    env = {**os.environ, "SHOPLITE_DB": str(db_file), "PORT": str(args.port)}
    base = f"http://127.0.0.1:{args.port}"

    subprocess.run([python, "seed.py"], cwd=args.app_dir, env=env, check=True, stdout=subprocess.DEVNULL)
    server = subprocess.Popen([python, "app.py"], cwd=args.app_dir, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_until_up(base, server)
        proc = psutil.Process(server.pid)

        # --- Load phase -----------------------------------------------------
        get_json(base, "/stats/reset", "POST")
        per_endpoint = {e: {"requests": 0, "queries": 0, "server_ms": 0.0, "errors": 0} for e in ENDPOINTS}
        cpu_start = cpu_seconds(proc)
        t_start = time.perf_counter()

        for endpoint, path in workload(args.requests):
            stats = per_endpoint[endpoint]
            stats["requests"] += 1
            try:
                with urllib.request.urlopen(base + path) as resp:
                    resp.read()
                    stats["queries"] += int(resp.headers["X-DB-Queries"])
                    stats["server_ms"] += float(resp.headers["X-Elapsed-Ms"])
            except OSError:
                stats["errors"] += 1

        runtime = time.perf_counter() - t_start
        cpu = cpu_seconds(proc) - cpu_start
        total_queries = get_json(base, "/stats/query-count")["total_queries"]

        # --- Idle phase: no requests, count any background work --------------
        get_json(base, "/stats/reset", "POST")
        idle_cpu_start = cpu_seconds(proc)
        time.sleep(args.idle)
        idle_cpu = cpu_seconds(proc) - idle_cpu_start
        idle_queries = get_json(base, "/stats/query-count")["total_queries"]
    finally:
        server.terminate()
        server.wait(timeout=10)
        db_file.unlink(missing_ok=True)
        db_file.parent.rmdir()

    request_queries = sum(s["queries"] for s in per_endpoint.values())
    errors = sum(s["errors"] for s in per_endpoint.values())
    print(f"  run {run_no}: {runtime:6.2f} s runtime, {cpu:6.2f} s server CPU, "
          f"{total_queries:,} queries, {idle_queries} idle queries"
          + (f", {errors} ERRORS" if errors else ""))

    return {
        "runtime_s": runtime,
        "server_cpu_s": cpu,
        "total_queries": total_queries,
        "request_queries": request_queries,
        "background_queries": total_queries - request_queries,
        "idle_queries": idle_queries,
        "idle_cpu_s": idle_cpu,
        "errors": errors,
        "endpoints": {
            e: {
                "requests": s["requests"],
                "queries_per_request": s["queries"] / s["requests"] if s["requests"] else 0,
                "avg_server_ms": s["server_ms"] / s["requests"] if s["requests"] else 0,
                "total_queries": s["queries"],
            }
            for e, s in per_endpoint.items()
        },
    }


def median_of(runs, key):
    return statistics.median(r[key] for r in runs)


def summarize(runs):
    summary = {k: median_of(runs, k) for k in
               ["runtime_s", "server_cpu_s", "total_queries", "request_queries",
                "background_queries", "idle_queries", "idle_cpu_s"]}
    summary["errors"] = sum(r["errors"] for r in runs)
    summary["endpoints"] = {
        e: {k: statistics.median(r["endpoints"][e][k] for r in runs) for k in runs[0]["endpoints"][e]}
        for e in ENDPOINTS
    }
    return summary


def git_info(app_dir):
    def git(*cmd):
        return subprocess.run(["git", *cmd], cwd=app_dir, capture_output=True, text=True).stdout.strip()
    return {
        "commit": git("rev-parse", "--short", "HEAD") or None,
        "uncommitted_changes": bool(git("status", "--porcelain", "--", ".")),
    }


def write_markdown(path, result):
    s, cfg, env = result["summary"], result["config"], result["environment"]
    lines = [
        f"# ShopLite load test: {result['label']}",
        "",
        f"{cfg['requests']:,} requests per run, median of {cfg['runs']} runs. "
        f"Recorded {result['timestamp']} on commit `{env['git']['commit']}`"
        + (" (with uncommitted changes)" if env["git"]["uncommitted_changes"] else "") + ".",
        "",
        "| Endpoint | Requests | Queries/request | Avg server ms | Total queries |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for e, d in s["endpoints"].items():
        lines.append(f"| `{e}` | {d['requests']:,.0f} | {d['queries_per_request']:,.1f} | "
                     f"{d['avg_server_ms']:,.1f} | {d['total_queries']:,.0f} |")
    lines += [
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total runtime | {s['runtime_s']:.2f} s |",
        f"| Server CPU time | {s['server_cpu_s']:.2f} s |",
        f"| Total DB queries | {s['total_queries']:,.0f} |",
        f"| ...from requests | {s['request_queries']:,.0f} |",
        f"| ...from background work | {s['background_queries']:,.0f} |",
        f"| Idle DB queries ({cfg['idle_s']:g} s, no requests) | {s['idle_queries']:,.0f} |",
        f"| Idle server CPU time | {s['idle_cpu_s']:.3f} s |",
        f"| Failed requests | {s['errors']} |",
        "",
        "Runtime and CPU time are proxies for energy use; query counts are exact.",
        "",
        f"Environment: Python {env['python']} on {env['platform']} ({env['cpu_count']} CPUs).",
        "",
    ]
    path.write_text("\n".join(lines))


def main():
    args = parse_args()
    args.app_dir = args.app_dir.resolve()
    python = args.python or str(args.app_dir / ".venv" / "bin" / "python")
    if not Path(python).exists():
        sys.exit(f"Python not found at {python}. Set up ShopLite first (see its README) or pass --python.")

    print(f"Load test '{args.label}': {args.runs} runs × {args.requests:,} requests, {args.idle:g} s idle window")
    runs = [run_once(args, python, i + 1) for i in range(args.runs)]

    result = {
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"requests": args.requests, "runs": args.runs, "idle_s": args.idle, "endpoints": ENDPOINTS},
        "environment": {
            "git": git_info(args.app_dir),
            "python": subprocess.run([python, "-c", "import platform; print(platform.python_version())"],
                                     capture_output=True, text=True).stdout.strip(),
            "platform": platform.platform(),
            "cpu_count": psutil.cpu_count(),
        },
        "summary": summarize(runs),
        "runs": runs,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.label}.json"
    md_path = args.out_dir / f"{args.label}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n")
    write_markdown(md_path, result)

    print(f"\nWrote {json_path} and {md_path.name}\n")
    print(md_path.read_text())


if __name__ == "__main__":
    main()
