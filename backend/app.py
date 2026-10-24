import hashlib
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from database import get_db_connection
from projects import projects_bp
from audit import audit_bp
from results import results_bp
from source_files import files_bp
from agent_api import agent_bp

app = Flask(__name__)
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

app.register_blueprint(projects_bp)
app.register_blueprint(audit_bp)
app.register_blueprint(results_bp)
app.register_blueprint(files_bp)
app.register_blueprint(agent_bp)


# Allow the UI to be opened from a file or another port during development
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# Serve the web UI at /ui
@app.route("/ui", methods=["GET"])
def ui():
    return send_from_directory(FRONTEND_DIR, "index.html")

# Home endpoint
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Welcome to GreenCode AI Backend",
        "description": "AI-powered code energy optimization",
        "status": "running"
    })

# Health check endpoint
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "GreenCode AI Backend"
    })


# INTENTIONALLY INEFFICIENT: N+1 QUERY PROBLEM
@app.route("/users/orders", methods=["GET"])
def get_users_orders():

    results = []
    query_count = 0

    with get_db_connection() as conn:

        # Query 1: Retrieve all users
        users = conn.execute(
            "SELECT id, name, email FROM users ORDER BY id"
        ).fetchall()

        query_count += 1

        # Inefficient: One additional query per user
        for user in users:

            orders = conn.execute(
                """
                SELECT id, user_id, product, price
                FROM orders
                WHERE user_id = ?
                ORDER BY id
                """,
                (user["id"],)
            ).fetchall()

            query_count += 1

            results.append({
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "orders": [dict(order) for order in orders]
            })

    total_orders = sum(
        len(user["orders"]) for user in results
    )

    response = jsonify({
        "total_users": len(results),
        "total_orders": total_orders,
        "users": results
    })

    # Expose query count for benchmarking
    response.headers["X-DB-Select-Count"] = str(query_count)

    return response

# INTENTIONALLY INEFFICIENT: Repeated calculations
def calculate_product_fingerprint(product, price):
    data = f"{product}:{price:.2f}".encode()

    # Simulate an expensive deterministic operation
    for _ in range(250):
        data = hashlib.sha256(data).digest()

    return data.hex()


@app.route("/analytics", methods=["GET"])
def get_analytics():

    with get_db_connection() as conn:
        orders = conn.execute(
            """
            SELECT id, product, price
            FROM orders
            ORDER BY id
            """
        ).fetchall()

    product_summary = {}
    calculation_count = 0

    for order in orders:
        product = order["product"]
        price = order["price"]

        # INEFFICIENT: Recalculates identical fingerprints
        fingerprint = calculate_product_fingerprint(
            product, price
        )

        calculation_count += 1

        if product not in product_summary:
            product_summary[product] = {
                "product": product,
                "price": price,
                "fingerprint": fingerprint,
                "orders": 0
            }

        product_summary[product]["orders"] += 1

    response = jsonify({
        "total_orders": len(orders),
        "unique_products": len(product_summary),
        "products": list(product_summary.values())
    })

    response.headers["X-Fingerprint-Calculations"] = str(
        calculation_count
    )

    return response

if __name__ == "__main__":
    # The reloader is off because the agent writes files inside the repo while it
    # runs, and a restart would wipe the in-memory run state.
    app.run(debug=True, use_reloader=False, port=5050)
