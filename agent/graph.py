"""GreenCode LangGraph agent — graph definition.

Workflow
────────
  detect → protect → propose → [INTERRUPT] human_approval
       → apply → verify → measure → report

The graph pauses at `human_approval` so a developer can review and
approve/reject each proposed patch before any code is touched.

Checkpointing
─────────────
The graph uses an in-memory `MemorySaver` by default.  Pass
`checkpointer=SqliteSaver(...)` for persistence across CLI sessions.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes.detect import detect
from agent.nodes.protect import protect
from agent.nodes.propose import propose
from agent.nodes.human_approval import human_approval
from agent.nodes.apply import apply_patches
from agent.nodes.verify import verify
from agent.nodes.measure import measure
from agent.nodes.report import report


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def _after_verify(state: AgentState) -> Literal["measure", "report"]:
    """If tests failed after patching, skip measurement and go straight to report."""
    result = state.get("post_apply_tests", {})
    if result.get("failed", 0) > 0 or result.get("errors", 0) > 0:
        print(
            "[graph] Post-patch tests not all green — "
            "skipping benchmark and going straight to report."
        )
        return "report"
    return "measure"


def _after_approval(state: AgentState) -> Literal["apply", "report"]:
    """If every proposal was rejected, skip apply/verify/measure and go to report."""
    decisions = state.get("decisions", [])
    if not any(d["approved"] for d in decisions):
        print("[graph] No proposals approved — skipping apply/verify/measure.")
        return "report"
    return "apply"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph(checkpointer=None):
    """Return a compiled LangGraph StateGraph.

    Parameters
    ----------
    checkpointer:
        Optional LangGraph checkpointer (MemorySaver, SqliteSaver, …).
        Defaults to a new MemorySaver so state survives the interrupt.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("detect", detect)
    builder.add_node("protect", protect)
    builder.add_node("propose", propose)
    builder.add_node("human_approval", human_approval)
    builder.add_node("apply", apply_patches)
    builder.add_node("verify", verify)
    builder.add_node("measure", measure)
    builder.add_node("report", report)

    # Edges
    builder.add_edge(START, "detect")
    builder.add_edge("detect", "protect")
    builder.add_edge("protect", "propose")
    builder.add_edge("propose", "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        _after_approval,
        {"apply": "apply", "report": "report"},
    )

    builder.add_edge("apply", "verify")

    builder.add_conditional_edges(
        "verify",
        _after_verify,
        {"measure": "measure", "report": "report"},
    )

    builder.add_edge("measure", "report")
    builder.add_edge("report", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval"],
    )
