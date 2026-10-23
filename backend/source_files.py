from flask import Blueprint, jsonify, request
from pathlib import Path
import re

from projects import load_projects

files_bp = Blueprint("source_files", __name__)

STORAGE_DIR = Path(__file__).resolve().parent / "data" / "source_files"
MAX_FILE_BYTES = 200_000


def project_exists(project_id):
    return any(
        project["id"] == project_id
        for project in load_projects()
    )


def get_safe_path(project_id, filename):
    if not isinstance(filename, str) or len(filename) > 200:
        return None

    if "\\" in filename:
        return None

    parts = filename.split("/")

    if any(
        part in ("", ".", "..") or
        not re.fullmatch(r"[A-Za-z0-9._-]+", part)
        for part in parts
    ):
        return None

    if not filename.endswith(".py"):
        return None

    project_dir = (STORAGE_DIR / project_id).resolve()
    target = project_dir.joinpath(*parts).resolve()

    if not target.is_relative_to(project_dir):
        return None

    return target


# Upload a Python source file
@files_bp.route("/api/projects/<project_id>/files", methods=["POST"])
def upload_source_file(project_id):

    if not project_exists(project_id):
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "JSON required"}), 400

    filename = data.get("path")
    content = data.get("content")

    target = get_safe_path(project_id, filename)

    if target is None:
        return jsonify({"error": "Invalid Python file path"}), 400

    if not isinstance(content, str):
        return jsonify({"error": "Source content must be text"}), 400

    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return jsonify({"error": "Source file is too large"}), 413

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return jsonify({
        "message": "Source file uploaded successfully",
        "project_id": project_id,
        "file": filename,
        "size_bytes": len(content.encode("utf-8"))
    }), 201


# List uploaded source files
@files_bp.route("/api/projects/<project_id>/files", methods=["GET"])
def list_source_files(project_id):

    if not project_exists(project_id):
        return jsonify({"error": "Project not found"}), 404

    project_dir = STORAGE_DIR / project_id

    if not project_dir.exists():
        return jsonify({"files": [], "total_files": 0}), 200

    files = sorted(
        str(path.relative_to(project_dir))
        for path in project_dir.rglob("*.py")
        if path.is_file()
    )

    return jsonify({
        "project_id": project_id,
        "files": files,
        "total_files": len(files)
    }), 200


# Retrieve source code for auditing
@files_bp.route(
    "/api/projects/<project_id>/files/<path:filename>",
    methods=["GET"]
)
def get_source_file(project_id, filename):

    if not project_exists(project_id):
        return jsonify({"error": "Project not found"}), 404

    target = get_safe_path(project_id, filename)

    if target is None or not target.is_file():
        return jsonify({"error": "File not found"}), 404

    return jsonify({
        "project_id": project_id,
        "file": filename,
        "content": target.read_text(encoding="utf-8")
    }), 200
