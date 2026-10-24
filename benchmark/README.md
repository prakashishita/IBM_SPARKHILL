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

## Energy and CO₂ estimate

By default the load phase is also tracked with [codecarbon](https://github.com/mlco2/codecarbon) in offline mode (no network calls). It reports estimated energy (Wh) and CO₂ (g). Treat both as estimates:

- Without `sudo`, codecarbon can't read real power on a Mac. It multiplies CPU load by the chip's typical power and adds RAM.
- It measures the whole machine, not only ShopLite, so close other busy apps while measuring. Single runs can vary by 50% or more; the median of 3 helps.
- CO₂ depends on the electricity grid. The default is `--country USA --region california`; change these to match where you are.

Use `--no-energy` to skip it. Runtime, CPU time and query counts remain the main numbers.

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
