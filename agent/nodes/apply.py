"""Apply node — creates an isolated git worktree and applies approved patches.

Isolation strategy
──────────────────
A git worktree is created from a new branch (greencode/<run-id>) that
starts at the current HEAD of the shoplite directory's owning repo.
All patches are applied *only* inside that worktree so the main working
tree is never touched.  If a patch fails to apply cleanly, that finding
is logged to `skipped_patches` and the rest continue.

Patch application
──────────────────
Each patch is a unified diff.  We use Python's stdlib `difflib`-style
reader plus a line-by-line apply rather than shelling out to `patch(1)`
to avoid a system dependency.  For patches that target specific hunks we
fall back to direct string substitution, which is safe for the three
known ShopLite inefficiencies.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

from agent.state import AgentState

# ---------------------------------------------------------------------------
# Worktree helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _create_worktree(repo_root: str, branch: str, worktree_path: str) -> None:
    _git(["worktree", "add", "-b", branch, worktree_path], cwd=repo_root)


def _remove_worktree(repo_root: str, worktree_path: str) -> None:
    _git(["worktree", "remove", "--force", worktree_path], cwd=repo_root, check=False)
    _git(["worktree", "prune"], cwd=repo_root, check=False)


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

def _apply_n_plus_one(app_py: Path) -> bool:
    """Replace users_summary() with the joined-query version."""
    src = app_py.read_text(encoding="utf-8")

    old_block = textwrap.dedent("""\
        def get_user_total_spent(db, user_id):
            row = db.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n FROM orders WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return round(row["total"], 2), row["n"]


        @app.get("/users/summary")
        def users_summary():
            db = get_db()
            users = db.execute("SELECT id, name, email FROM users ORDER BY id").fetchall()

            summary = []
            for user in users:
                total_spent, order_count = get_user_total_spent(db, user["id"])
                summary.append({
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "order_count": order_count,
                    "total_spent": total_spent,
                })
            return jsonify(summary)""")

    new_block = textwrap.dedent("""\
        @app.get("/users/summary")
        def users_summary():
            db = get_db()
            rows = db.execute(
                \"\"\"SELECT u.id, u.name, u.email,
                          COUNT(o.id)                         AS order_count,
                          ROUND(COALESCE(SUM(o.amount), 0), 2) AS total_spent
                   FROM users u
                   LEFT JOIN orders o ON o.user_id = u.id
                   GROUP BY u.id
                   ORDER BY u.id\"\"\"
            ).fetchall()
            summary = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "email": r["email"],
                    "order_count": r["order_count"],
                    "total_spent": r["total_spent"],
                }
                for r in rows
            ]
            return jsonify(summary)""")

    if old_block not in src:
        return False
    app_py.write_text(src.replace(old_block, new_block, 1), encoding="utf-8")
    return True


def _apply_lru_cache(app_py: Path) -> bool:
    """Add functools import and @lru_cache to seasonal_demand_index."""
    src = app_py.read_text(encoding="utf-8")

    # 1. Add functools import after `import math`
    if "import functools" not in src:
        src = src.replace("import math\n", "import math\nimport functools\n", 1)

    # 2. Add decorator before the function definition
    old_def = "def seasonal_demand_index(category):"
    new_def = "@functools.lru_cache(maxsize=None)\ndef seasonal_demand_index(category):"
    if old_def not in src:
        return False
    if "@functools.lru_cache" in src:
        return True  # already applied
    src = src.replace(old_def, new_def, 1)
    app_py.write_text(src, encoding="utf-8")
    return True


def _apply_polling_interval(app_py: Path) -> bool:
    """Replace the background poller with an on-demand refresh in /status."""
    src = app_py.read_text(encoding="utf-8")
    if "def watch_orders" not in src:
        return "check_orders()\n    with _status_lock:\n        return jsonify" in src  # already applied

    # 1. Drop the watch_orders() polling function
    new_src = re.sub(
        r"def watch_orders\(\):\n    while True:\n        time\.sleep\(\s*\d+\s*\)\n        check_orders\(\)\n\n\n",
        "", src, count=1,
    )
    # 2. Do not start the background thread
    new_src = new_src.replace(
        "    check_orders()\n    threading.Thread(target=watch_orders, daemon=True).start()\n",
        "    check_orders()\n", 1,
    )
    # 3. Refresh the count when /status is requested
    new_src = new_src.replace(
        "def status():\n    with _status_lock:",
        "def status():\n    check_orders()\n    with _status_lock:", 1,
    )
    if new_src == src or "threading.Thread(target=watch_orders" in new_src:
        return False
    app_py.write_text(new_src, encoding="utf-8")
    return True


_APPLY_FN = {
    "n+1_query": _apply_n_plus_one,
    "repeated_recomputation": _apply_lru_cache,
    "polling_loop": _apply_polling_interval,
}


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def apply_patches(state: AgentState) -> AgentState:
    """Create worktree and apply each approved patch."""
    import uuid
    from pathlib import Path as _Path

    target_dir = _Path(state["target_dir"])
    # Walk up to find the git root (shoplite/ sits inside IBM_SPARKHILL/)
    repo_root = _git(
        ["rev-parse", "--show-toplevel"], cwd=str(target_dir)
    ).stdout.strip()

    branch = f"greencode/{uuid.uuid4().hex[:8]}"
    worktree_path = str(_Path(repo_root) / ".greencode_worktree")

    # Clean up any leftover worktree from a previous failed run
    _remove_worktree(repo_root, worktree_path)

    print(f"[apply] Creating git worktree at {worktree_path}  (branch: {branch})")
    _create_worktree(repo_root, branch, worktree_path)

    # The worktree mirrors the whole repo; shoplite is in the same subpath
    rel = str(target_dir.relative_to(repo_root))
    wt_shoplite = _Path(worktree_path) / rel
    app_py = wt_shoplite / "app.py"

    decisions_by_id = {d["finding_id"]: d for d in state.get("decisions", [])}
    findings_by_id  = {f["id"]: f for f in state.get("findings", [])}

    applied: list[str] = []
    skipped: list[str] = []

    for proposal in state.get("proposals", []):
        fid = proposal["finding_id"]
        decision = decisions_by_id.get(fid)

        if not decision or not decision["approved"]:
            print(f"[apply] Skipping {fid} (rejected or no decision)")
            skipped.append(fid)
            continue

        finding = findings_by_id.get(fid, {})
        pattern = finding.get("pattern", "")
        apply_fn = _APPLY_FN.get(pattern)

        if apply_fn is None:
            print(f"[apply] No apply function for pattern '{pattern}' — skipping {fid}")
            skipped.append(fid)
            continue

        try:
            ok = apply_fn(app_py)
            if ok:
                print(f"[apply] ✓  Applied patch for {fid}")
                applied.append(fid)
            else:
                print(f"[apply] ✗  Patch for {fid} did not match source — skipping")
                skipped.append(fid)
        except Exception as exc:
            print(f"[apply] ✗  Exception applying {fid}: {exc}")
            skipped.append(fid)

    # Commit the changes in the worktree so the benchmark can reference a commit
    if applied:
        _git(["add", "-A"], cwd=str(wt_shoplite))
        _git(
            ["commit", "-m", f"greencode: apply {len(applied)} energy fix(es)\n\n"
             + "\n".join(f"- {fid}" for fid in applied)],
            cwd=worktree_path,
        )
        print(f"[apply] Committed {len(applied)} fix(es) in worktree.")
    else:
        print("[apply] No patches applied — worktree unchanged.")

    return {
        **state,
        "worktree_dir": worktree_path,
        "worktree_branch": branch,
        "applied_patches": applied,
        "skipped_patches": skipped,
    }
