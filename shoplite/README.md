# ShopLite

A small online store backend with 200 customers, 50 products and about 2,000 orders, built with Flask and SQLite. It comes with a browser dashboard and reports the database queries and server time of every request.

## Requirements

- Python 3.9 or newer

## Setup

Run these from the `shoplite/` folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py
```

`seed.py` creates `app.db` with the sample data. It always generates the same data, so re-run it any time to reset the database.

## Run the app

```bash
.venv/bin/python app.py
```

Open **http://127.0.0.1:5000/** in your browser. Stop the server with Ctrl+C.

To use a different port: `PORT=5055 .venv/bin/python app.py`

> **macOS:** use `127.0.0.1` rather than `localhost`. The AirPlay Receiver can also listen on port 5000 and answer instead of ShopLite.

## Check that it works

With the server running, open a second terminal and run:

```bash
.venv/bin/python check.py
```

It calls every endpoint once and prints the status, query count and time for each. It ends with `7/7 endpoints OK` and exits with a non-zero code if any endpoint fails. Use `BASE_URL=http://127.0.0.1:5055` if the server runs on another port.

`check.py` places one real order. Run `seed.py` again to reset.

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/` | Browser dashboard |
| GET | `/api` | List of endpoints (JSON) |
| GET | `/users/summary` | All customers with order count and total spent |
| GET | `/users/<id>` | One customer and their orders |
| GET | `/products/report` | Products with units sold, demand index and score |
| POST | `/orders` | Create an order: `{"user_id": 1, "product_id": 3, "quantity": 2}` |
| GET | `/status` | Current order count and latest order ID |
| GET | `/stats/query-count` | Total database queries since the server started |
| POST | `/stats/reset` | Reset that total to 0 |

Every response includes two headers:

- `X-DB-Queries`: database queries run for that request
- `X-Elapsed-Ms`: server time for that request, in milliseconds

See them with `curl -i http://127.0.0.1:5000/users/summary`.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Flask app and endpoints |
| `database.py` | SQLite connection, schema and query counting |
| `seed.py` | Creates `app.db` with sample data |
| `check.py` | Calls every endpoint and reports the results |
| `static/index.html` | Browser dashboard |
