from flask import Blueprint, jsonify, request
from pathlib import Path
import json
import uuid

projects_bp = Blueprint("projects", __name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PROJECTS_FILE = DATA_DIR / "projects.json"


def load_projects():
    if not PROJECTS_FILE.exists():
        return []

    with open(PROJECTS_FILE, "r") as file:
        return json.load(file)


def save_projects(projects):
    with open(PROJECTS_FILE, "w") as file:
        json.dump(projects, file, indent=4)


# Register a project
@projects_bp.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    name = data.get("name")
    language = data.get("language", "python")

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Project name is required"}), 400

    if not isinstance(language, str) or not language.strip():
        return jsonify({"error": "Valid language is required"}), 400

    project = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "language": language.strip().lower(),
        "status": "registered"
    }

    projects = load_projects()
    projects.append(project)
    save_projects(projects)

    return jsonify({
        "message": "Project registered successfully",
        "project": project
    }), 201


# List registered projects
@projects_bp.route("/api/projects", methods=["GET"])
def get_projects():
    return jsonify({
        "projects": load_projects()
    }), 200


# Retrieve one project
@projects_bp.route("/api/projects/<project_id>", methods=["GET"])
def get_project(project_id):
    for project in load_projects():
        if project["id"] == project_id:
            return jsonify(project), 200

    return jsonify({"error": "Project not found"}), 404
