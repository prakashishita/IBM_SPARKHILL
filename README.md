# GreenCode AI

**An AI agent that finds energy waste in code, drafts the fix, and only changes anything after a human approves it.**

Software that runs the same wasteful query 200 times per request burns real electricity, in every data center, on every request. GreenCode AI audits a codebase for those patterns, proposes a patch for each one, waits for a developer's approval, applies approved patches in an isolated git worktree, checks that behaviour is unchanged, and measures the energy saved.

## How it works

```
detect → protect → propose → [ human approval ] → apply → verify → measure → report
```

| Step | What happens |
| --- | --- |
| Find waste | Static analysis finds N+1 queries, polling loops and repeated computation, with file and line |
| Write safety tests | Generates a behaviour test suite for the target app before anything changes |
| Draft fixes | One patch per finding, as a unified diff with a plain-language rationale |
| **Your review** | The agent pauses (LangGraph interrupt). You approve or reject each fix in the web UI |
| Apply fixes | Approved patches go into a separate git worktree. Your working tree is never touched |
| Re-run tests | If any safety test fails, the agent skips measurement and reports it |
| Measure energy | Same load test before and after: query counts (exact), CPU time, estimated energy and CO₂ (codecarbon) |
| Write report | Markdown and HTML report with every decision and the measured savings |

## Demo target: ShopLite

`shoplite/` is a small store API with three deliberate inefficiencies. In the recorded baseline, 1,000 requests cause **68,207 database queries**; 98% come from one endpoint (`/users/summary`, 201 queries per request) and 93% of server CPU time comes from another (`/products/report`).

After the three approved fixes the same load test makes **1,333 queries** (−98%) and the 23 safety tests pass. Query counts are exact and the same on any machine. Time, energy and CO₂ are estimates from the machine that ran the benchmark, so compare a baseline and an "after" recorded on the same machine.

## Run it

```bash
# 1. ShopLite environment (used by the tests and the benchmark)
python3 -m venv shoplite/.venv && shoplite/.venv/bin/pip install -r shoplite/requirements.txt

# 2. Backend + agent
pip install -r backend/requirements.txt -r agent/requirements.txt pytest
pip install -r benchmark/requirements.txt          # only needed for the energy measurement

# 3. Start the app
python backend/app.py                               # open http://localhost:5050/ui
```

Click **Run audit**, review the proposed diffs, approve what you want, and watch the results fill in. The measure step takes a few minutes.

Requirements: a git checkout with `git config user.name` and `user.email` set (the apply step commits in a worktree).

If the backend isn't running, `frontend/index.html` opens in demo mode with the real findings and patches and clearly labelled sample numbers.

Prefer the terminal? `python -m agent.cli run --target shoplite/` then `python -m agent.cli resume --approve-all`.

## Repo layout

| Folder | Purpose |
| --- | --- |
| `agent/` | LangGraph agent: one node per step in `agent/nodes/`, graph in `agent/graph.py`, CLI in `agent/cli.py` |
| `backend/` | Flask API: projects, files, findings, results, plus `agent_api.py` which runs the agent for the UI |
| `frontend/` | Single-file web UI, served at `/ui` |
| `shoplite/` | The app being audited |
| `benchmark/` | Fixed load test and the recorded baseline |

## Responsible AI

- **Human control.** Every change needs an explicit approval. Undecided fixes are skipped, never auto-applied.
- **Transparency.** Each finding and patch comes with a plain-language reason; each decision and its note goes into the report.
- **Safety.** Patches run in an isolated worktree and must pass a behaviour test suite before any benchmark counts.
- **Privacy.** The code you audit stays on your machine. The only outside request the UI makes is loading the Google Fonts stylesheet.

## Built with

Python, LangGraph, Flask, pytest, codecarbon, and IBM Bob for planning, test generation and code review.
