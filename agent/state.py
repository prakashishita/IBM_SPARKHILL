"""Shared state schema for the GreenCode LangGraph agent.

Every node reads and writes a single AgentState TypedDict that flows
through the graph.  All fields are optional so each node can be tested
in isolation without constructing the full state.
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

class Finding(TypedDict):
    """One energy-inefficiency finding from the Detect node."""
    id: str                   # slug, e.g. "n_plus_one_users_summary"
    file: str                 # relative path inside the target repo
    line: Optional[int]       # first affected line (None if span)
    pattern: str              # short label: "n+1_query" | "polling_loop" | "repeated_recomputation"
    description: str          # human-readable explanation
    energy_impact: str        # "high" | "medium" | "low"
    suggestion: str           # one-sentence fix strategy


class Proposal(TypedDict):
    """A concrete patch proposed by the Propose node for one finding."""
    finding_id: str
    patch: str        # unified diff (--- a/ +++ b/ format)
    rationale: str    # why this patch fixes the waste


class ApprovalDecision(TypedDict):
    """The human reviewer's verdict on a single proposal."""
    finding_id: str
    approved: bool
    note: str         # free-text reviewer comment (may be empty)


class TestResult(TypedDict):
    """Outcome of running the test suite."""
    passed: int
    failed: int
    errors: int
    output: str       # raw pytest stdout (truncated to 8 KB)


class BenchmarkResult(TypedDict):
    """Summary metrics from one loadtest.py run."""
    label: str
    runtime_s: float
    server_cpu_s: float
    total_queries: int
    idle_queries: int
    energy_wh: Optional[float]
    co2_g: Optional[float]
    raw_json_path: str   # absolute path to the full JSON file


# ---------------------------------------------------------------------------
# Top-level state
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    # --- inputs -------------------------------------------------------
    target_dir: str          # absolute path to shoplite/
    benchmark_dir: str       # absolute path to benchmark/
    worktree_dir: str        # absolute path to the git worktree
    worktree_branch: str     # git branch name used by the worktree

    # --- detect -------------------------------------------------------
    findings: list[Finding]

    # --- protect ------------------------------------------------------
    tests_dir: str           # absolute path where generated tests live
    baseline_tests: TestResult

    # --- propose ------------------------------------------------------
    proposals: list[Proposal]

    # --- human approval -----------------------------------------------
    decisions: list[ApprovalDecision]

    # --- apply --------------------------------------------------------
    applied_patches: list[str]   # finding_ids successfully applied
    skipped_patches: list[str]   # finding_ids skipped (rejected or failed)

    # --- verify -------------------------------------------------------
    post_apply_tests: TestResult

    # --- measure ------------------------------------------------------
    baseline_benchmark: BenchmarkResult
    after_benchmark: BenchmarkResult

    # --- report -------------------------------------------------------
    report_path: str         # absolute path to the written report file

    # --- control flow -------------------------------------------------
    error: Optional[str]     # set by any node on unrecoverable failure
    interrupted: bool        # True while waiting for human approval
