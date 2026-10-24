from flask import Blueprint, jsonify, request
from pathlib import Path
import json
import uuid
import math

from projects import load_projects

results_bp = Blueprint("results", __name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

RESULTS_FILE = DATA_DIR / "results.json"

ALLOWED_METRICS = {
    "runtime_ms",
    "cpu_time_ms",
    "db_queries",
    "fingerprint_calculations"
}

COUNT_METRICS = {
    "db_queries",
    "fingerprint_calculations"
}


def load_results():
    if not RESULTS_FILE.exists():
        return []

    with open(RESULTS_FILE, "r") as file:
        return json.load(file)


def save_results(results):
    with open(RESULTS_FILE, "w") as file:
        json.dump(results, file, indent=4)


# Save before or after performance measurements
@results_bp.route("/api/results", methods=["POST"])
def create_result():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "A JSON object is required"
        }), 400

    project_id = data.get("project_id")
    phase = data.get("phase")
    endpoint = data.get("endpoint")
    metrics = data.get("metrics")

    if not isinstance(project_id, str):
        return jsonify({
            "error": "Valid project_id required"
        }), 400

    if not any(
        p["id"] == project_id
        for p in load_projects()
    ):
        return jsonify({
            "error": "Project not found"
        }), 404

    if phase not in ("before", "after"):
        return jsonify({
            "error": "Phase must be before or after"
        }), 400

    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        return jsonify({
            "error": "Valid endpoint required"
        }), 400

    if not isinstance(metrics, dict) or not metrics:
        return jsonify({
            "error": "Metrics object is required"
        }), 400

    for name, value in metrics.items():
        if name not in ALLOWED_METRICS:
            return jsonify({
                "error": f"Unsupported metric: {name}"
            }), 400

        if (isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0):
            return jsonify({
                "error": f"Invalid value for {name}"
            }), 400

        if name in COUNT_METRICS and not (
            isinstance(value, int)
        ):
            return jsonify({
                "error": f"{name} must be an integer"
            }), 400

    result = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "phase": phase,
        "endpoint": endpoint,
        "metrics": metrics
    }

    results = load_results()
    results.append(result)
    save_results(results)

    return jsonify({
        "message": "Benchmark result saved",
        "result": result
    }), 201


# Get stored benchmark results
@results_bp.route("/api/results", methods=["GET"])
def get_results():
    results = load_results()

    project_id = request.args.get("project_id")
    endpoint = request.args.get("endpoint")

    if project_id:
        results = [
            r for r in results
            if r["project_id"] == project_id
        ]

    if endpoint:
        results = [
            r for r in results
            if r["endpoint"] == endpoint
        ]

    return jsonify({
        "total_results": len(results),
        "results": results
    }), 200
