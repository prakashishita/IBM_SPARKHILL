from flask import Blueprint, jsonify, request
from pathlib import Path
import json
import uuid

from projects import load_projects

audit_bp = Blueprint("audit", __name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

FINDINGS_FILE = DATA_DIR / "findings.json"


def load_findings():
    if not FINDINGS_FILE.exists():
        return []

    with open(FINDINGS_FILE, "r") as file:
        return json.load(file)


def save_findings(findings):
    with open(FINDINGS_FILE, "w") as file:
        json.dump(findings, file, indent=4)


# Store a finding from IBM Bob
@audit_bp.route("/api/audit", methods=["POST"])
def create_audit_finding():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    required = ["project_id", "file", "issue", "suggestion"]

    if any(
        not isinstance(data.get(field), str)
        or not data[field].strip()
        for field in required
    ):
        return jsonify({
            "error": "project_id, file, issue and suggestion are required"
        }), 400

    if not any(
        p["id"] == data["project_id"]
        for p in load_projects()
    ):
        return jsonify({"error": "Project not found"}), 404

    finding = {
        "id": str(uuid.uuid4()),
        "project_id": data["project_id"],
        "file": data["file"],
        "line": data.get("line"),
        "issue": data["issue"],
        "suggestion": data["suggestion"],
        "status": "detected"
    }

    findings = load_findings()
    findings.append(finding)
    save_findings(findings)

    return jsonify({
        "message": "Audit finding saved",
        "finding": finding
    }), 201


# Get findings, optionally filtered by project
@audit_bp.route("/api/findings", methods=["GET"])
def get_findings():
    findings = load_findings()
    project_id = request.args.get("project_id")

    if project_id:
        findings = [
            f for f in findings
            if f["project_id"] == project_id
        ]

    return jsonify({
        "total_findings": len(findings),
        "findings": findings
    }), 200

# Request optimization of a detected finding
@audit_bp.route("/api/optimize", methods=["POST"])
def request_optimization():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "A JSON object is required"
        }), 400

    finding_id = data.get("finding_id")

    if not isinstance(finding_id, str) or not finding_id:
        return jsonify({
            "error": "finding_id is required"
        }), 400

    findings = load_findings()

    for finding in findings:
        if finding["id"] == finding_id:

            if finding["status"] != "detected":
                return jsonify({
                    "error": "Optimization already requested"
                }), 409

            finding["status"] = "optimization_requested"
            save_findings(findings)

            return jsonify({
                "message": "Optimization request created",
                "finding": finding
            }), 200

    return jsonify({
        "error": "Finding not found"
    }), 404
