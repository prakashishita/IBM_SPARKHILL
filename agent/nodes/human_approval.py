"""Human Approval node — presents proposals to a reviewer and records verdicts.

The graph is configured with interrupt_before=["human_approval"] so LangGraph
pauses execution here.  The CLI resume path calls graph.invoke() with the
decisions pre-loaded into state; this node validates and normalises them.

Two modes:
  - Interactive (default): prints each proposal and waits for stdin input.
  - Batch / CI: if state["decisions"] is already populated, skips prompting
    and just validates + echoes what was supplied.
"""

from __future__ import annotations

import textwrap

from agent.state import AgentState, ApprovalDecision

_WIDTH = 78


def _box(title: str, body: str) -> str:
    border = "─" * _WIDTH
    lines = [f"┌{border}┐", f"│  {title:<{_WIDTH - 2}}│"]
    for line in body.splitlines():
        for wrapped in textwrap.wrap(line, _WIDTH - 4) or [""]:
            lines.append(f"│  {wrapped:<{_WIDTH - 4}}  │")
    lines.append(f"└{border}┘")
    return "\n".join(lines)


def _print_proposal(idx: int, total: int, finding: dict, proposal: dict) -> None:
    print()
    print(_box(
        f"Proposal {idx}/{total}  [{finding['energy_impact'].upper()} impact]  "
        f"id={proposal['finding_id']}",
        f"Pattern : {finding['pattern']}\n"
        f"File    : {finding['file']}  line {finding['line']}\n"
        f"Problem : {finding['description']}\n"
        f"\nRationale:\n{proposal['rationale']}\n"
        f"\nProposed patch:\n{proposal['patch']}",
    ))


def human_approval(state: AgentState) -> AgentState:
    """Collect approval/rejection for each proposal.

    If `decisions` is already set in state (e.g. fed in by the resume call),
    validate the list and return immediately — this supports non-interactive
    (CI / scripted) use.
    """
    proposals = state.get("proposals", [])
    findings_by_id = {f["id"]: f for f in state.get("findings", [])}

    # -- Non-interactive path: decisions were injected by the caller ----------
    pre_set = state.get("decisions")
    if pre_set:
        decided_ids = {d["finding_id"] for d in pre_set}
        # Fill in any missing proposals as auto-approved
        decisions: list[ApprovalDecision] = list(pre_set)
        for p in proposals:
            if p["finding_id"] not in decided_ids:
                decisions.append(ApprovalDecision(
                    finding_id=p["finding_id"],
                    approved=True,
                    note="auto-approved (not in pre-set decisions)",
                ))
        _summarise(decisions)
        return {**state, "decisions": decisions}

    # -- Interactive path: prompt the human -----------------------------------
    if not proposals:
        print("[approval] No proposals to review.")
        return {**state, "decisions": []}

    decisions = []
    total = len(proposals)
    for idx, proposal in enumerate(proposals, start=1):
        finding = findings_by_id.get(proposal["finding_id"], {})
        _print_proposal(idx, total, finding, proposal)

        while True:
            raw = input("\nApprove this fix? [y/n/s(kip)] > ").strip().lower()
            if raw in ("y", "yes", ""):
                approved = True
                note = input("Optional note (Enter to skip): ").strip()
                break
            elif raw in ("n", "no"):
                approved = False
                note = input("Reason for rejection: ").strip()
                break
            elif raw in ("s", "skip"):
                approved = False
                note = "skipped by reviewer"
                break
            else:
                print("Please enter y, n, or s.")

        decisions.append(ApprovalDecision(
            finding_id=proposal["finding_id"],
            approved=approved,
            note=note,
        ))

    print()
    _summarise(decisions)
    return {**state, "decisions": decisions}


def _summarise(decisions: list[ApprovalDecision]) -> None:
    approved = [d for d in decisions if d["approved"]]
    rejected = [d for d in decisions if not d["approved"]]
    print(f"[approval] {len(approved)} approved, {len(rejected)} rejected.")
    for d in approved:
        print(f"  ✓  {d['finding_id']}")
    for d in rejected:
        print(f"  ✗  {d['finding_id']}  — {d['note']}")
