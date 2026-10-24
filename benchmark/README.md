# Benchmark

Measures ShopLite before and after Bob's fixes: total runtime, server CPU time and database queries. Runtime and CPU time are proxies for energy use; query counts are exact.

This folder is the fixed measuring tool. Keep it out of Bob's audit and refactors so the before and after numbers stay comparable.

## Setup

ShopLite must be set up first (see `../shoplite/README.md`). Then, from this folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Record a measurement

```bash
.venv/bin/python loadtest.py --label baseline   # before the fixes (already recorded)
.venv/bin/python loadtest.py --label after      # after the fixes
```

Each run takes about 2.5 minutes. The script:

1. seeds a private temporary database, so your own `shoplite/app.db` is untouched
2. starts ShopLite on port 5077
3. sends 1,000 requests, round-robin across `/users/summary`, `/products/report` and `/users/<id>`
4. waits 10 seconds with no requests and counts any background queries
5. stops the server

It repeats this 3 times and reports the median. Results go to `results/<label>.json` (raw data) and `results/<label>.md` (readable table).

Options: `--requests`, `--runs`, `--idle`, `--port`. Run `.venv/bin/python loadtest.py --help` for details.

## Compare before and after

```bash
.venv/bin/python compare.py
```

This prints the percentage change for each metric and writes `results/comparison.md`.

## Re-measuring the original code

The baseline was recorded on the code at the `baseline` git tag. To measure it again later:

```bash
git checkout baseline
.venv/bin/python loadtest.py --label baseline
git checkout -
```
