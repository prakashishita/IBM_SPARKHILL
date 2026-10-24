# GreenCode AI frontend

One file, no build step: `frontend/index.html`.

## Run it

```bash
pip install -r backend/requirements.txt -r agent/requirements.txt
python backend/app.py          # http://localhost:5050
```

Open **http://localhost:5050/ui**. The agent runs inside the Flask process, so the run state
survives between "Run audit" and your approval.

If the backend is not running, the page opens in **demo mode** (banner shown): real findings,
real patches and the real baseline from `benchmark/results/baseline.json`, with *sample*
"after" numbers that are clearly labelled as not measured.

## What each screen does

| Screen | Backend it uses |
| --- | --- |
| Overview: where queries and CPU time go, before/after bars | `GET /api/benchmark` |
| Findings | `GET /api/agent/status` |
| Review: diff, approve/reject, note | `POST /api/agent/decisions` |
| Results: before/after table, tests, applied/skipped | `GET /api/agent/status`, `GET /api/benchmark` |
| Report | `GET /api/agent/report` |
| Source files: register project, upload `.py` | `/api/projects`, `/api/projects/<id>/files` |

## Backend changes (small)

- `backend/agent_api.py` (new): runs the LangGraph agent in a background thread and exposes
  `/api/agent/run`, `/api/agent/status`, `/api/agent/decisions`, `/api/agent/report`, `/api/benchmark`.
- `backend/app.py`: registers that blueprint, adds CORS headers, serves the UI at `/ui`, and turns
  the Flask reloader off (the agent writes files in the repo, and a reload wipes the run state).

## Needs to be true on your machine

- The repo is a git checkout with a configured `git user.name` / `user.email` (the apply step commits in a worktree).
- `pytest` is installed (the safety tests and the verify step use it).
- For the "after" benchmark: the `benchmark/` requirements (codecarbon etc.). The measure step takes a few minutes.
