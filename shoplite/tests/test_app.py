import os
import sys
from pathlib import Path

# Prevent the background watcher from running during tests
os.environ["SHOPLITE_DISABLE_WATCHER"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app import app


app.config["TESTING"] = True
import pytest


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

def test_api_endpoint(client):
    response = client.get("/api")

    assert response.status_code == 200

    data = response.get_json()
    assert data["app"] == "ShopLite"
    assert len(data["endpoints"]) == 7


def test_users_summary(client):
    response = client.get("/users/summary")

    assert response.status_code == 200

    users = response.get_json()
    assert len(users) == 200
    assert "id" in users[0]
    assert "name" in users[0]
    assert "email" in users[0]
    assert "order_count" in users[0]
    assert "total_spent" in users[0]


def test_single_user(client):
    response = client.get("/users/1")

    assert response.status_code == 200

    user = response.get_json()
    assert user["id"] == 1
    assert "name" in user
    assert "email" in user
    assert "orders" in user
    assert isinstance(user["orders"], list)


def test_missing_user_returns_404(client):
    response = client.get("/users/999999")

    assert response.status_code == 404
    assert response.get_json()["error"] == "user not found"


def test_products_report(client):
    response = client.get("/products/report")

    assert response.status_code == 200

    data = response.get_json()
    assert "products" in data
    assert len(data["products"]) == 50

    product = data["products"][0]
    assert "id" in product
    assert "name" in product
    assert "units_sold" in product
    assert "demand_index" in product
    assert "score" in product


def test_invalid_order_returns_400(client):
    response = client.post("/orders", json={})

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_status_endpoint(client):
    response = client.get("/status")

    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"
    assert "order_count" in data
    assert "latest_order_id" in data


def test_create_order(client):
    response = client.post(
        "/orders",
        json={
            "user_id": 1,
            "product_id": 3,
            "quantity": 2,
        },
    )

    assert response.status_code == 201

    order = response.get_json()
    assert order["user_id"] == 1
    assert order["product_id"] == 3
    assert order["quantity"] == 2
    assert "amount" in order
    assert "id" in order