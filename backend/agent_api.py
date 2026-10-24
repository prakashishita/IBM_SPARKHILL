"""Bridge between the web UI and the GreenCode LangGraph agent.

Endpoints
---------
GET  /api/agent/status     current run state: step, findings, proposals, decisions
POST /api/agent/run        start a pipeline run (pauses before human approval)
POST /api/agent/decisions  submit approve/reject verdicts and resume the run
GET  /api/agent/report     the finished report (markdown)
GET  /api/benchmark        baseline / after benchmark summaries

The agent runs in a background thread inside this Flask process, so the
in-memory LangGraph checkpointer survives between `run` and `decisions`.
"""

import json
import sys
import threading
import traceback
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request

WORKSPACE = Path(__file__).resolve().parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

agent_bp = Blueprint("agent_api", __name__)

# The agent writes findings and reports to slightly different folders,
# so look in both.
DATA_DIRS = [WORKSPACE / "agent" / "data", WORKSPACE / "agent" / "agent" / "data"]
RESULTS_DIR = WORKSPACE / "benchmark" / "results"

PIPELINE = ["detect", "protect", "propose", "human_approval",
            "apply", "verify", "measure", "report"]

_lock = threading.Lock()
_graph = None
_run = {
    "status": "idle",      # idle | running | awaiting_approval | applying | done | error
    "thread_id": None,
    "step": None,          # last node that finished
    "completed": [],
    "error": None,
    "findings": [],
    "proposals": [],
    "decisions": [],
    "applied": [],
    "skipped": [],
    "post_apply_tests": None,
}


def _get_graph():
    global _graph
    if _graph is None:
        from agent.graph import build_graph  # imported lazily: needs langgraph
        _graph = build_graph()
    return _graph


def _snapshot():
    with _lock:
        return json.loads(json.dumps(_run))


def _update(**kwargs):
    with _lock:
        _run.update(kwargs)


def _stream(graph, payload, config):
    """Run the graph, recording each node as it completes."""
    for event in graph.stream(payload, config=config, stream_mode="updates"):
        for node in event:
            if node.startswith("__"):
                continue
            with _lock:
                if node not in _run["completed"]:
                    _run["completed"].append(node)
                _run["step"] = node


def _pull_state(graph, config):
    values = graph.get_state(config).values
    _update(
        findings=values.get("findings", []),
        proposals=values.get("proposals", []),
        decisions=values.get("decisions", []),
        applied=values.get("applied_patches", []),
        skipped=values.get("skipped_patches", []),
        post_apply_tests=values.get("post_apply_tests"),
    )
    return values


def _safe_pull():
    """Keep whatever the agent produced before a failure so the UI can show it."""
    try:
        _pull_state(_get_graph(), {"configurable": {"thread_id": _run["thread_id"]}})
    except Exception:
        pass


def _run_pipeline(target):
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": _run["thread_id"]}}
        _stream(graph, {"target_dir": target,
                        "benchmark_dir": str(WORKSPACE / "benchmark")}, config)
        _pull_state(graph, config)
        _update(status="awaiting_approval")
    except Exception as exc:  # surfaced to the UI
        traceback.print_exc()
        _safe_pull()
        _update(status="error", error=f"{type(exc).__name__}: {exc}")


def _resume_pipeline(decisions):
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": _run["thread_id"]}}
        graph.update_state(config, {"decisions": decisions}, as_node="human_approval")
        with _lock:
            if "human_approval" not in _run["completed"]:
                _run["completed"].append("human_approval")
        _stream(graph, None, config)
        _pull_state(graph, config)
        _update(status="done")
    except Exception as exc:
        traceback.print_exc()
        _safe_pull()
        _update(status="error", error=f"{type(exc).__name__}: {exc}")


@agent_bp.route("/api/agent/status", methods=["GET"])
def agent_status():
    snap = _snapshot()
    snap["pipeline"] = PIPELINE
    snap["report_available"] = _find_report("report.md") is not None
    return jsonify(snap), 200


@agent_bp.route("/api/agent/run", methods=["POST"])
def agent_run():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        return jsonify({"error": "langgraph is not installed. Run: pip install -r agent/requirements.txt"}), 503

    with _lock:
        if _run["status"] in ("running", "applying"):
            return jsonify({"error": "A run is already in progress"}), 409

    body = request.get_json(silent=True) or {}
    target = Path(body.get("target") or WORKSPACE / "shoplite")
    if not target.is_absolute():
        target = (WORKSPACE / target).resolve()
    if not target.is_dir():
        return jsonify({"error": f"Target directory not found: {target}"}), 400

    with _lock:
        _run.update({
            "status": "running", "thread_id": f"greencode-{uuid.uuid4().hex[:8]}",
            "step": None, "completed": [], "error": None, "findings": [],
            "proposals": [], "decisions": [], "applied": [], "skipped": [],
            "post_apply_tests": None,
        })

    threading.Thread(target=_run_pipeline, args=(str(target),), daemon=True).start()
    return jsonify({"message": "Run started", "thread_id": _run["thread_id"]}), 202


@agent_bp.route("/api/agent/decisions", methods=["POST"])
def agent_decisions():
    with _lock:
        if _run["status"] != "awaiting_approval":
            return jsonify({"error": "No run is waiting for approval"}), 409
        proposal_ids = {p["finding_id"] for p in _run["proposals"]}

    body = request.get_json(silent=True)
    raw = body.get("decisions") if isinstance(body, dict) else None
    if not isinstance(raw, list) or not raw:
        return jsonify({"error": "decisions must be a non-empty list"}), 400

    decisions = []
    for d in raw:
        fid = d.get("finding_id") if isinstance(d, dict) else None
        if fid not in proposal_ids or not isinstance(d.get("approved"), bool):
            return jsonify({"error": f"Invalid decision for {fid}"}), 400
        decisions.append({
            "finding_id": fid,
            "approved": d["approved"],
            "note": str(d.get("note", ""))[:500],
        })

    # Anything the reviewer did not decide is rejected, never auto-approved.
    decided = {d["finding_id"] for d in decisions}
    for fid in proposal_ids - decided:
        decisions.append({"finding_id": fid, "approved": False, "note": "not reviewed"})

    _update(status="applying", decisions=decisions)
    threading.Thread(target=_resume_pipeline, args=(decisions,), daemon=True).start()
    return jsonify({"message": "Decisions recorded, resuming run"}), 202


def _find_report(name):
    for d in DATA_DIRS:
        p = d / name
        if p.is_file():
            return p
    return None


@agent_bp.route("/api/agent/report", methods=["GET"])
def agent_report():
    md = _find_report("report.md")
    if md is None:
        return jsonify({"error": "No report yet. Finish a run first."}), 404
    return jsonify({"markdown": md.read_text(encoding="utf-8")}), 200


def _load_summary(label):
    path = RESULTS_DIR / f"{label}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"label": label, "timestamp": data.get("timestamp"),
            "config": data.get("config"), "summary": data.get("summary")}


@agent_bp.route("/api/benchmark", methods=["GET"])
def benchmark():
    return jsonify({"baseline": _load_summary("baseline"),
                    "after": _load_summary("after")}), 200
