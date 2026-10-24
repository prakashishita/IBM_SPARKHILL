"""Create app.db and fill it with deterministic sample data.

Usage: python seed.py
"""

import os
import random
from datetime import datetime, timedelta

import database

NUM_USERS = 200
NUM_PRODUCTS = 50
ORDERS_PER_USER = 10

FIRST_NAMES = [
    "Alice", "Bob", "Chen", "Divya", "Elena", "Farid", "Grace", "Hiro", "Isla", "Jonas",
    "Kemi", "Liam", "Maya", "Noah", "Olu", "Priya", "Quinn", "Ravi", "Sofia", "Tariq",
]
LAST_NAMES = [
    "Okafor", "Patel", "Nguyen", "Garcia", "Smith", "Kowalski", "Haddad", "Tanaka", "Silva", "Müller",
]
CATEGORIES = ["electronics", "books", "garden", "kitchen", "toys"]
PRODUCT_WORDS = ["Widget", "Gadget", "Kit", "Set", "Pack", "Tool", "Lamp", "Box", "Mat", "Case"]
ADJECTIVES = ["Mini", "Pro", "Eco", "Smart", "Classic"]

START_DATE = datetime(2026, 1, 1)


def seed():
    random.seed(42)

    if os.path.exists(database.DB_PATH):
        os.remove(database.DB_PATH)

    conn = database.connect()
    print("Creating schema...")
    database.init_schema(conn)

    users = []
    for i in range(1, NUM_USERS + 1):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        created = START_DATE + timedelta(days=random.randint(0, 180))
        users.append((i, f"{first} {last}", f"{first.lower()}.{last.lower()}{i}@example.com",
                      created.date().isoformat()))
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", users)
    print(f"Inserted {len(users)} users")

    products = []
    for i in range(1, NUM_PRODUCTS + 1):
        name = f"{random.choice(ADJECTIVES)} {random.choice(PRODUCT_WORDS)} {i}"
        products.append((i, name, CATEGORIES[i % len(CATEGORIES)], round(random.uniform(5, 250), 2)))
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)
    print(f"Inserted {len(products)} products")

    prices = {p[0]: p[3] for p in products}
    orders = []
    order_id = 1
    for user_id in range(1, NUM_USERS + 1):
        for _ in range(ORDERS_PER_USER):
            product_id = random.randint(1, NUM_PRODUCTS)
            quantity = random.randint(1, 5)
            created = START_DATE + timedelta(days=random.randint(0, 290), minutes=random.randint(0, 1439))
            orders.append((order_id, user_id, product_id, quantity,
                           round(prices[product_id] * quantity, 2), created.isoformat()))
            order_id += 1
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", orders)
    print(f"Inserted {len(orders):,} orders ({ORDERS_PER_USER} per user)")

    conn.commit()
    conn.close()
    print(f"Done → {database.DB_PATH}")


if __name__ == "__main__":
    seed()
