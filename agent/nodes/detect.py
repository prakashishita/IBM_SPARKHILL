"""Detect node — scans the ShopLite source tree for energy-wasteful patterns.

This is a pure static analyser.  It does NOT call an LLM; every pattern
is detected by deterministic AST / regex rules so the results are
reproducible and fast.  The three planted inefficiencies in ShopLite are:

  1. N+1 query  (users_summary: per-user DB call inside a loop)
  2. Polling loop  (watch_orders: while True: sleep(1))
  3. Repeated recomputation  (products_report: seasonal_demand_index
       called once per row with no memoisation)

The node writes `agent/data/findings.json` so downstream nodes (and Bob
in Ask mode) can inspect the structured output without re-running the scan.
"""

from __future__ import annotations

import ast
import json
import re
import uuid
from pathlib import Path

from agent.state import AgentState, Finding

DATA_DIR = Path(__file__).resolve().parent.parent / "agent" / "data"

# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------

def _detect_n_plus_one(source: str, rel_path: str) -> list[Finding]:
    """Find DB execute() calls (direct or via helper) inside for-loops.

    Detects two forms:
      1. Direct: db.execute() called inside a for-loop body.
      2. Indirect: a function that itself calls db.execute() is called
         inside a for-loop (N+1 via helper delegation).
    """
    findings: list[Finding] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    # Collect names of functions that call db/conn .execute() directly
    db_calling_fns: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(getattr(child, "func", None), ast.Attribute)
                and child.func.attr == "execute"  # type: ignore[attr-defined]
            ):
                db_calling_fns.add(node.name)
                break

    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        for child in ast.walk(node):
            if child is node:
                continue
            # Form 1: direct db.execute() inside the loop
            direct_hit = (
                isinstance(child, ast.Call)
                and isinstance(getattr(child, "func", None), ast.Attribute)
                and child.func.attr == "execute"  # type: ignore[attr-defined]
            )
            # Form 2: call to a function that issues execute() itself
            indirect_hit = (
                isinstance(child, ast.Call)
                and isinstance(getattr(child, "func", None), ast.Name)
                and child.func.id in db_calling_fns  # type: ignore[attr-defined]
            )
            if direct_hit or indirect_hit:
                hint = (
                    f"at line {child.lineno}"
                    if direct_hit
                    else f"(via `{child.func.id}`) at line {child.lineno}"  # type: ignore[attr-defined]
                )
                findings.append(Finding(
                    id=f"n_plus_one_{rel_path.replace('/', '_').replace('.py', '')}",
                    file=rel_path,
                    line=node.lineno,
                    pattern="n+1_query",
                    description=(
                        f"A DB execute() call {hint} sits inside a "
                        f"for-loop that starts at line {node.lineno}. "
                        "Each loop iteration issues a separate SQL query, producing "
                        "N+1 round-trips to the database (one to fetch the list, "
                        "then one per row). With 200 users this is 201 queries per "
                        "request instead of 1."
                    ),
                    energy_impact="high",
                    suggestion=(
                        "Replace the loop with a single JOIN query that fetches "
                        "users and their aggregated order totals in one SQL statement."
                    ),
                ))
                break  # one finding per for-loop is enough
    return findings


def _detect_polling_loop(source: str, rel_path: str) -> list[Finding]:
    """Find while True: ... sleep(...) patterns."""
    findings: list[Finding] = []
    # Simple regex: function containing while True and a sleep() call
    fn_pattern = re.compile(
        r"def\s+(\w+)\s*\([^)]*\).*?(?=\ndef\s|\Z)",
        re.DOTALL,
    )
    for m in fn_pattern.finditer(source):
        body = m.group(0)
        if re.search(r"while\s+True", body) and re.search(r"time\.sleep\s*\(", body):
            # Find line number
            line = source[: m.start()].count("\n") + 1
            fn_name = m.group(1)
            findings.append(Finding(
                id=f"polling_loop_{fn_name}",
                file=rel_path,
                line=line,
                pattern="polling_loop",
                description=(
                    f"Function `{fn_name}` at line {line} uses a tight "
                    "`while True: sleep(1)` polling loop that wakes the CPU "
                    "every second even when there is nothing to do.  Over a "
                    "10-second idle window this fires ~10 unnecessary DB queries "
                    "and burns idle CPU continuously."
                ),
                energy_impact="medium",
                suggestion=(
                    "Increase the poll interval to 30 s, or replace the pattern "
                    "with a threading.Event / APScheduler job so the watcher only "
                    "fires when genuinely needed."
                ),
            ))
    return findings


def _detect_repeated_recomputation(source: str, rel_path: str) -> list[Finding]:
    """Find expensive functions called inside loops with no caching."""
    findings: list[Finding] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    # Collect function names that do heavy numeric work (>= 2 nested for-loops)
    heavy_fns: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for_count = sum(1 for n in ast.walk(node) if isinstance(n, ast.For))
        if for_count >= 2:
            heavy_fns.add(node.name)

    # Now find call sites of those functions inside another for-loop
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        for child in ast.walk(node):
            if child is node:
                continue
            if (
                isinstance(child, ast.Call)
                and isinstance(getattr(child, "func", None), ast.Name)
                and child.func.id in heavy_fns   # type: ignore[attr-defined]
            ):
                fn = child.func.id  # type: ignore[attr-defined]
                findings.append(Finding(
                    id=f"recompute_{fn}",
                    file=rel_path,
                    line=node.lineno,
                    pattern="repeated_recomputation",
                    description=(
                        f"`{fn}` performs a double nested loop (7,680 iterations) "
                        "and is called once per product row at line "
                        f"{child.lineno} with no memoisation. "
                        "With 50 products and 5 distinct categories the same "
                        "computation repeats ~40 times unnecessarily."
                    ),
                    energy_impact="high",
                    suggestion=(
                        f"Decorate `{fn}` with `@functools.lru_cache(maxsize=None)` "
                        "or pre-compute a category→index dict before the loop."
                    ),
                ))
                break
    return findings


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def detect(state: AgentState) -> AgentState:
    """Walk every .py file in target_dir and apply all pattern detectors."""
    target = Path(state["target_dir"])
    all_findings: list[Finding] = []
    seen_ids: set[str] = set()

    for py_file in sorted(target.rglob("*.py")):
        rel = str(py_file.relative_to(target))
        source = py_file.read_text(encoding="utf-8")

        detectors = [
            _detect_n_plus_one,
            _detect_polling_loop,
            _detect_repeated_recomputation,
        ]
        for detector in detectors:
            for finding in detector(source, rel):
                # Deduplicate by id (a file may match multiple detectors)
                base_id = finding["id"]
                unique_id = base_id
                suffix = 1
                while unique_id in seen_ids:
                    unique_id = f"{base_id}_{suffix}"
                    suffix += 1
                finding["id"] = unique_id
                seen_ids.add(unique_id)
                all_findings.append(finding)

    # Persist to disk so other tools (Bob Ask mode, CI scripts) can read it
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    findings_path = DATA_DIR / "findings.json"
    findings_path.write_text(
        json.dumps(all_findings, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[detect] Found {len(all_findings)} inefficiency pattern(s).")
    for f in all_findings:
        print(f"  [{f['energy_impact'].upper()}] {f['pattern']}  {f['file']}:{f['line']}  — {f['id']}")

    return {**state, "findings": all_findings}
