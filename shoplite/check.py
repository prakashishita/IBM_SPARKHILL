"""Call every ShopLite endpoint once and print what came back.

Usage: python check.py            (server must be running)
       BASE_URL=http://127.0.0.1:5055 python check.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")

CHECKS = [
    ("GET", "/api", None, lambda d: f"{len(d['endpoints'])} endpoints listed"),
    ("GET", "/users/summary", None, lambda d: f"{len(d)} users, first: {d[0]['name']} spent {d[0]['total_spent']}"),
    ("GET", "/users/1", None, lambda d: f"{d['name']} with {len(d['orders'])} orders"),
    ("GET", "/products/report", None, lambda d: f"{len(d['products'])} products, top score {max(p['score'] for p in d['products'])}"),
    ("POST", "/orders", {"user_id": 1, "product_id": 3, "quantity": 2}, lambda d: f"created order {d['id']} for {d['amount']}"),
    ("GET", "/status", None, lambda d: f"{d['order_count']} orders, latest id {d['latest_order_id']}"),
    ("GET", "/stats/query-count", None, lambda d: f"{d['total_queries']} queries since startup"),
]


def call(method, path, body):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.headers, json.load(resp)
    except urllib.error.HTTPError as err:
        return err.code, err.headers, None


def main():
    try:
        urllib.request.urlopen(BASE_URL + "/", timeout=2)
    except OSError:
        sys.exit(f"Cannot reach {BASE_URL}. Start the server first: python app.py")

    print(f"Checking ShopLite at {BASE_URL}\n")
    print(f"{'':2}{'METHOD':<7}{'PATH':<20}{'STATUS':>6}{'QUERIES':>9}{'MS':>8}   RESULT")
    failures = 0
    for method, path, body, describe in CHECKS:
        status, headers, data = call(method, path, body)
        ok = 200 <= status < 300 and data is not None
        failures += not ok
        result = describe(data) if ok else "FAILED"
        print(f"{'✓' if ok else '✗':2}{method:<7}{path:<20}{status:>6}"
              f"{headers.get('X-DB-Queries', '-'):>9}{headers.get('X-Elapsed-Ms', '-'):>8}   {result}")

    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} endpoints OK")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
