"""Propose node — generates a concrete unified-diff patch for each finding.

Patches are hand-coded (deterministic) because the three planted
inefficiencies in ShopLite are known in advance.  This keeps the demo
fully reproducible without requiring an LLM API key.

Each patch is expressed as a standard unified diff (--- a/ +++ b/ format)
so the Apply node can use Python's `patch` library or `git apply` to
materialise the change in the worktree without any string manipulation.
"""

from __future__ import annotations

from agent.state import AgentState, Proposal

# ---------------------------------------------------------------------------
# Hard-coded patches for the three planted inefficiencies
# ---------------------------------------------------------------------------

# ---  1. N+1 query  ---------------------------------------------------------
# Replace the per-user get_user_total_spent() call inside the loop with a
# single aggregating JOIN.

_PATCH_N_PLUS_ONE = """\
--- a/app.py
+++ b/app.py
@@ -58,18 +58,22 @@
-def get_user_total_spent(db, user_id):
-    row = db.execute(
-        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n FROM orders WHERE user_id = ?",
-        (user_id,),
-    ).fetchone()
-    return round(row["total"], 2), row["n"]
-
-
 @app.get("/users/summary")
 def users_summary():
     db = get_db()
-    users = db.execute("SELECT id, name, email FROM users ORDER BY id").fetchall()
-
-    summary = []
-    for user in users:
-        total_spent, order_count = get_user_total_spent(db, user["id"])
-        summary.append({
-            "id": user["id"],
-            "name": user["name"],
-            "email": user["email"],
-            "order_count": order_count,
-            "total_spent": total_spent,
-        })
+    rows = db.execute(
+        \"\"\"SELECT u.id, u.name, u.email,
+                  COUNT(o.id)                    AS order_count,
+                  ROUND(COALESCE(SUM(o.amount), 0), 2) AS total_spent
+           FROM users u
+           LEFT JOIN orders o ON o.user_id = u.id
+           GROUP BY u.id
+           ORDER BY u.id\"\"\"
+    ).fetchall()
+    summary = [
+        {
+            "id": r["id"],
+            "name": r["name"],
+            "email": r["email"],
+            "order_count": r["order_count"],
+            "total_spent": r["total_spent"],
+        }
+        for r in rows
+    ]
     return jsonify(summary)
"""

# ---  2. Repeated recomputation  -------------------------------------------
# Add @functools.lru_cache to seasonal_demand_index and import functools.

_PATCH_RECOMPUTE = """\
--- a/app.py
+++ b/app.py
@@ -1,7 +1,8 @@
 import math
+import functools
 import os
 import threading
 import time
 from datetime import datetime
 
 from flask import Flask, g, jsonify, request
@@ -104,6 +105,7 @@
 
+@functools.lru_cache(maxsize=None)
 def seasonal_demand_index(category):
     \"\"\"Demand multiplier for a category over the Q4 peak season (15-minute resolution).\"\"\"
     phase = sum(ord(c) for c in category) % 365
"""

# ---  3. Polling loop  -------------------------------------------------------
# Increase the poll interval from 1 s to 30 s to reduce idle CPU and DB load.

_PATCH_POLLING = """\
--- a/app.py
+++ b/app.py
@@ -202,7 +202,7 @@
 def watch_orders():
     while True:
-        time.sleep(1)
+        time.sleep(30)
         check_orders()
"""

# ---------------------------------------------------------------------------
# Mapping from finding pattern → patch
# ---------------------------------------------------------------------------

_PATCHES: dict[str, tuple[str, str]] = {
    "n+1_query": (
        _PATCH_N_PLUS_ONE,
        "Replace 201 per-request DB round-trips with a single LEFT JOIN + GROUP BY "
        "aggregation. The original code calls get_user_total_spent() once for each "
        "of the 200 users, each call executing one SQL SELECT. The fix issues exactly "
        "one query regardless of how many users exist.",
    ),
    "repeated_recomputation": (
        _PATCH_RECOMPUTE,
        "Add @functools.lru_cache(maxsize=None) to seasonal_demand_index(). "
        "ShopLite has 5 distinct product categories, so the cache is warm after "
        "the first 5 calls. Subsequent calls in the same process return instantly "
        "instead of executing 7,680 floating-point iterations.",
    ),
    "polling_loop": (
        _PATCH_POLLING,
        "Increase the watch_orders() sleep interval from 1 s to 30 s. "
        "The /status endpoint serves cached data; 1-second resolution adds no "
        "observable value but fires ~20 unnecessary DB queries per 10-second idle "
        "window and keeps a CPU timer ticking continuously.",
    ),
}


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def propose(state: AgentState) -> AgentState:
    """Attach a patch proposal to every finding that has a known fix."""
    findings = state.get("findings", [])
    proposals: list[Proposal] = []

    for finding in findings:
        pattern = finding["pattern"]
        if pattern not in _PATCHES:
            print(f"[propose] No patch template for pattern '{pattern}' — skipping {finding['id']}")
            continue

        patch_text, rationale = _PATCHES[pattern]
        proposals.append(Proposal(
            finding_id=finding["id"],
            patch=patch_text,
            rationale=rationale,
        ))
        print(f"[propose] Generated patch for {finding['id']}  ({pattern})")

    print(f"[propose] {len(proposals)} proposal(s) ready for human review.")
    return {**state, "proposals": proposals}
