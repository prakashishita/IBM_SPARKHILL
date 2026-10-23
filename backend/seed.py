from database import initialize_database, get_db_connection

PRODUCTS = [
    ("Laptop", 999.99),
    ("Keyboard", 79.99),
    ("Mouse", 39.99),
    ("Monitor", 299.99),
    ("Headphones", 149.99)
]


def seed_database():
    initialize_database()

    with get_db_connection() as conn:

        # Clear old sample data
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM users")

        # Create 200 sample users
        users = [
            (f"User {i}", f"user{i}@example.com")
            for i in range(1, 201)
        ]

        conn.executemany(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            users
        )

        # Retrieve the IDs of inserted users
        user_ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM users")
        ]

        # Create 5 orders for every user
        orders = []

        for user_id in user_ids:
            for product, price in PRODUCTS:
                orders.append((user_id, product, price))

        conn.executemany(
            """
            INSERT INTO orders (user_id, product, price)
            VALUES (?, ?, ?)
            """,
            orders
        )

        total_users = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        total_orders = conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]

    print("Database seeded successfully!")
    print(f"Total users: {total_users}")
    print(f"Total orders: {total_orders}")


if __name__ == "__main__":
    seed_database()
