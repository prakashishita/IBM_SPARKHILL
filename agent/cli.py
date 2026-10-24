"""GreenCode Agent — command-line interface.

Usage
─────
  # Run the full pipeline (pauses for human review at the approval step)
  python -m agent.cli run --target shoplite/

  # Resume after reviewing proposals (approve all)
  python -m agent.cli resume --approve-all --thread <thread-id>

  # Resume with selective approval (comma-separated finding IDs)
  python -m agent.cli resume --approve n_plus_one_app,recompute_seasonal_demand_index

  # Skip the benchmark (faster demo run)
  python -m agent.cli run --target shoplite/ --no-measure

  # Show the findings from the last detect run
  python -m agent.cli show-findings

  # Show the last report
  python -m agent.cli show-report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow `python -m agent.cli` from the workspace root
_WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WORKSPACE))

from agent.graph import build_graph
from agent.state import AgentState, ApprovalDecision

DATA_DIR = _WORKSPACE / "agent" / "data"
THREAD_FILE = DATA_DIR / ".last_thread_id"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_thread(thread_id: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    THREAD_FILE.write_text(thread_id, encoding="utf-8")


def _load_thread() -> str | None:
    if THREAD_FILE.exists():
        return THREAD_FILE.read_text(encoding="utf-8").strip()
    return None


def _resolve_target(raw: str) -> str:
    p = Path(raw)
    if not p.is_absolute():
        p = (_WORKSPACE / p).resolve()
    if not p.is_dir():
        sys.exit(f"Target directory not found: {p}")
    return str(p)


def _print_section(title: str, body: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")
    print(body)


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    """Start a new pipeline run (pauses before human_approval)."""
    target = _resolve_target(args.target)
    benchmark = str(_WORKSPACE / "benchmark")
    thread_id = f"greencode-{os.urandom(4).hex()}"

    print(f"\n🌿 GreenCode Agent — starting run  (thread: {thread_id})")
    print(f"   Target : {target}")
    print(f"   Thread : {thread_id}")

    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "target_dir": target,
        "benchmark_dir": benchmark,
    }

    # Stream events so the user sees progress in real time
    for event in graph.stream(initial_state, config=config, stream_mode="values"):
        pass  # progress is printed inside each node

    # After the interrupt the graph has paused — show the proposals
    snapshot = graph.get_state(config)
    state = snapshot.values
    proposals = state.get("proposals", [])
    findings = {f["id"]: f for f in state.get("findings", [])}

    _print_section(
        f"⏸  Paused for human approval  ({len(proposals)} proposal(s))",
        "",
    )
    for i, p in enumerate(proposals, 1):
        f = findings.get(p["finding_id"], {})
        print(
            f"  [{i}] {p['finding_id']}\n"
            f"       Pattern : {f.get('pattern', '?')}\n"
            f"       File    : {f.get('file', '?')} line {f.get('line', '?')}\n"
            f"       Impact  : {f.get('energy_impact', '?').upper()}\n"
            f"       Rationale: {p['rationale'][:120]}…\n"
        )

    _save_thread(thread_id)
    print(
        f"Thread ID saved.  Resume with:\n"
        f"  python -m agent.cli resume --approve-all --thread {thread_id}\n"
        f"  python -m agent.cli resume --approve <id1,id2> --thread {thread_id}\n"
        f"  python -m agent.cli resume --reject-all --thread {thread_id}\n"
    )


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume the pipeline after human review."""
    thread_id = args.thread or _load_thread()
    if not thread_id:
        sys.exit("No thread ID given and no saved thread found. Run `agent.cli run` first.")

    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # Fetch the suspended state to get the proposal list
    snapshot = graph.get_state(config)
    state = snapshot.values
    proposals = state.get("proposals", [])

    if not proposals:
        sys.exit("No proposals found in state. Has `run` completed up to the approval step?")

    # Build decisions from CLI flags
    all_ids = [p["finding_id"] for p in proposals]

    if args.reject_all:
        decisions = [
            ApprovalDecision(finding_id=fid, approved=False, note="rejected via --reject-all")
            for fid in all_ids
        ]
    elif args.approve_all:
        decisions = [
            ApprovalDecision(finding_id=fid, approved=True, note="approved via --approve-all")
            for fid in all_ids
        ]
    elif args.approve:
        approved_set = set(args.approve.split(","))
        decisions = [
            ApprovalDecision(
                finding_id=fid,
                approved=fid in approved_set,
                note="approved via --approve" if fid in approved_set else "not in --approve list",
            )
            for fid in all_ids
        ]
    else:
        sys.exit("Specify one of --approve-all, --reject-all, or --approve <id1,id2>")

    # Inject decisions and resume
    print(f"\n🌿 GreenCode Agent — resuming thread {thread_id}")
    update = {"decisions": decisions}
    graph.update_state(config, update, as_node="human_approval")

    for event in graph.stream(None, config=config, stream_mode="values"):
        pass

    # Final state
    final = graph.get_state(config).values
    report_path = final.get("report_path", "")
    if report_path:
        print(f"\n✅  Report written → {report_path}")
        print(f"    HTML version → {report_path.replace('.md', '.html')}")
    else:
        print("\n⚠️  Run completed but no report path found in state.")


def cmd_show_findings(args: argparse.Namespace) -> None:
    path = DATA_DIR / "findings.json"
    if not path.exists():
        sys.exit("No findings.json found. Run `agent.cli run` first.")
    data = json.loads(path.read_text())
    print(json.dumps(data, indent=2))


def cmd_show_report(args: argparse.Namespace) -> None:
    path = DATA_DIR / "report.md"
    if not path.exists():
        sys.exit("No report.md found. Complete a full pipeline run first.")
    print(path.read_text())


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m agent.cli",
        description="GreenCode LangGraph agent CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Start a new audit pipeline run")
    p_run.add_argument(
        "--target", default="shoplite/",
        help="Path to the ShopLite directory (default: shoplite/)",
    )
    p_run.set_defaults(func=cmd_run)

    # resume
    p_resume = sub.add_parser("resume", help="Resume after human approval")
    p_resume.add_argument("--thread", default=None, help="Thread ID (defaults to last saved)")
    group = p_resume.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve-all", action="store_true", help="Approve all proposals")
    group.add_argument("--reject-all", action="store_true", help="Reject all proposals")
    group.add_argument("--approve", metavar="IDS", help="Comma-separated finding IDs to approve")
    p_resume.set_defaults(func=cmd_resume)

    # show-findings
    p_sf = sub.add_parser("show-findings", help="Print the last findings.json")
    p_sf.set_defaults(func=cmd_show_findings)

    # show-report
    p_sr = sub.add_parser("show-report", help="Print the last report.md")
    p_sr.set_defaults(func=cmd_show_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
