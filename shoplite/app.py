"""ShopLite: a small store API backed by SQLite.

Run:  python seed.py && python app.py
"""

import math
import os
import threading
import time
from datetime import datetime

from flask import Flask, g, jsonify, request

import database

app = Flask(__name__)
app.teardown_appcontext(database.close_db)


@app.before_request
def start_timer():
    g.start_time = time.perf_counter()


@app.after_request
def add_metrics_headers(response):
    elapsed_ms = (time.perf_counter() - g.start_time) * 1000
    response.headers["X-DB-Queries"] = str(database.request_query_count())
    response.headers["X-Elapsed-Ms"] = f"{elapsed_ms:.1f}"
    return response


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api")
def api_index():
    return jsonify({
        "app": "ShopLite",
        "endpoints": [
            "GET  /users/summary",
            "GET  /users/<id>",
            "GET  /products/report",
            "POST /orders",
            "GET  /status",
            "GET  /stats/query-count",
            "POST /stats/reset",
        ],
    })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

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
    return jsonify(summary)


@app.get("/users/<int:user_id>")
def user_detail(user_id):
    db = get_db()
    user = db.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return jsonify({"error": "user not found"}), 404

    orders = db.execute(
        """SELECT o.id, o.product_id, p.name AS product_name, o.quantity, o.amount, o.created_at
           FROM orders o JOIN products p ON p.id = o.product_id
           WHERE o.user_id = ? ORDER BY o.id""",
        (user_id,),
    ).fetchall()
    return jsonify({**dict(user), "orders": [dict(o) for o in orders]})


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def seasonal_demand_index(category):
    """Demand multiplier for a category over the Q4 peak season (15-minute resolution)."""
    phase = sum(ord(c) for c in category) % 365
    samples = 0
    total = 0.0
    for day in range(273, 365):
        for slot in range(96):
            t = (day + phase + slot / 96) / 365
            total += 1 + 0.35 * math.sin(2 * math.pi * t) + 0.1 * math.cos(14 * math.pi * t)
            samples += 1
    return total / samples


@app.get("/products/report")
def products_report():
    db = get_db()
    rows = db.execute(
        """SELECT p.id, p.name, p.category, p.price,
                  COALESCE(SUM(o.quantity), 0) AS units_sold
           FROM products p LEFT JOIN orders o ON o.product_id = p.id
           GROUP BY p.id ORDER BY p.id"""
    ).fetchall()

    report = []
    for row in rows:
        demand = seasonal_demand_index(row["category"])
        report.append({
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "price": row["price"],
            "units_sold": row["units_sold"],
            "demand_index": round(demand, 4),
            "score": round(row["units_sold"] * demand * math.log1p(row["price"]), 2),
        })
    return jsonify({"products": report})


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@app.post("/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    try:
        user_id = int(data["user_id"])
        product_id = int(data["product_id"])
        quantity = int(data.get("quantity", 1))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "user_id and product_id are required integers"}), 400
    if quantity < 1:
        return jsonify({"error": "quantity must be at least 1"}), 400

    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        return jsonify({"error": "user not found"}), 404
    product = db.execute("SELECT price FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        return jsonify({"error": "product not found"}), 404

    amount = round(product["price"] * quantity, 2)
    created_at = datetime.now().isoformat(timespec="seconds")
    cur = db.execute(
        "INSERT INTO orders (user_id, product_id, quantity, amount, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, product_id, quantity, amount, created_at),
    )
    db.commit()
    return jsonify({
        "id": cur.lastrowid,
        "user_id": user_id,
        "product_id": product_id,
        "quantity": quantity,
        "amount": amount,
        "created_at": created_at,
    }), 201


# ---------------------------------------------------------------------------
# Order status watcher
# ---------------------------------------------------------------------------

order_status = {"order_count": 0, "latest_order_id": None}
_status_lock = threading.Lock()


def check_orders():
    conn = database.connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        latest = conn.execute("SELECT MAX(id) FROM orders").fetchone()[0]
    finally:
        conn.close()
    with _status_lock:
        order_status["order_count"] = count
        order_status["latest_order_id"] = latest


def watch_orders():
    while True:
        time.sleep(1)
        check_orders()


def start_order_watcher():
    check_orders()
    threading.Thread(target=watch_orders, daemon=True).start()


@app.get("/status")
def status():
    with _status_lock:
        return jsonify({"status": "ok", **order_status})


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@app.get("/stats/query-count")
def query_count():
    return jsonify({"total_queries": database.total_query_count()})


@app.post("/stats/reset")
def reset_query_count():
    database.reset_total_query_count()
    return jsonify({"total_queries": 0})


def get_db():
    return database.get_db()


if os.environ.get("SHOPLITE_DISABLE_WATCHER") != "1":
    start_order_watcher()


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)), threaded=True)
