"""Measure node — runs the benchmark harness before and after the patches.

The loadtest.py script in benchmark/ is the canonical measurement tool.
This node invokes it twice:

  1. Baseline: against the original (unpatched) shoplite in target_dir.
     If a pre-recorded baseline.json already exists it is reused rather
     than re-running (the script takes ~2 min; skipping saves time in demos).

  2. After: against the patched shoplite in worktree_dir.

Both results are stored in benchmark/results/ and the paths are saved in
state so the Report node can read them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agent.state import AgentState, BenchmarkResult

_BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmark"
_RESULTS_DIR = _BENCHMARK_DIR / "results"


def _load_existing(label: str) -> BenchmarkResult | None:
    path = _RESULTS_DIR / f"{label}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        s = data["summary"]
        return BenchmarkResult(
            label=label,
            runtime_s=s["runtime_s"],
            server_cpu_s=s["server_cpu_s"],
            total_queries=int(s["total_queries"]),
            idle_queries=int(s["idle_queries"]),
            energy_wh=s.get("energy_wh"),
            co2_g=s.get("co2_g"),
            raw_json_path=str(path.resolve()),
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _run_loadtest(
    label: str,
    shoplite_dir: str,
    requests: int = 1000,
    runs: int = 3,
    energy: bool = True,
    app_python: str | None = None,
) -> BenchmarkResult:
    """Invoke benchmark/loadtest.py and parse the output JSON."""
    benchmark_python = _BENCHMARK_DIR / ".venv" / "bin" / "python"
    python = str(benchmark_python) if benchmark_python.exists() else sys.executable

    cmd = [
        python, str(_BENCHMARK_DIR / "loadtest.py"),
        "--label", label,
        "--app-dir", shoplite_dir,
        "--requests", str(requests),
        "--runs", str(runs),
        "--out-dir", str(_RESULTS_DIR),
    ]
    if app_python:
        # A git worktree has no .venv (it is gitignored), so reuse the original one.
        cmd += ["--python", app_python]
    if not energy:
        cmd.append("--no-energy")

    print(f"[measure] Running loadtest for label='{label}' ...")
    proc = subprocess.run(cmd, capture_output=False, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"loadtest.py exited with code {proc.returncode}")

    result = _load_existing(label)
    if result is None:
        raise RuntimeError(f"loadtest.py ran but {label}.json was not written")
    return result


def measure(state: AgentState) -> AgentState:
    """Record baseline and after-patch benchmark results."""
    target_dir = state["target_dir"]
    worktree_dir = state.get("worktree_dir", "")

    # -- Baseline -----------------------------------------------------------
    # Reuse the pre-recorded baseline.json if it exists (avoids a 2-min wait)
    baseline = _load_existing("baseline")
    if baseline is not None:
        print(
            f"[measure] Reusing pre-recorded baseline "
            f"({baseline['total_queries']:,} queries, "
            f"{baseline['runtime_s']:.1f} s runtime)"
        )
    else:
        print("[measure] No baseline.json found — running baseline load test...")
        baseline = _run_loadtest("baseline", target_dir)

    # -- After --------------------------------------------------------------
    if not worktree_dir:
        print("[measure] No worktree — cannot measure 'after'. Skipping.")
        return {**state, "baseline_benchmark": baseline}

    # Derive shoplite path in worktree
    from pathlib import Path as _Path
    target = _Path(target_dir)
    repo_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(target), capture_output=True, text=True,
    )
    repo_root = repo_root_result.stdout.strip()
    rel = str(target.relative_to(repo_root))
    wt_shoplite = str(_Path(worktree_dir) / rel)

    original_venv = target / ".venv" / "bin" / "python"
    app_python = str(original_venv) if original_venv.exists() else sys.executable
    after = _run_loadtest("after", wt_shoplite, app_python=app_python)
    print(
        f"[measure] After patch: {after['total_queries']:,} queries, "
        f"{after['runtime_s']:.1f} s runtime."
    )

    return {
        **state,
        "baseline_benchmark": baseline,
        "after_benchmark": after,
    }
