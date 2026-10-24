"""Report node — generates a structured Markdown + HTML evidence report.

The report combines:
  - Every finding and its status (approved, applied, skipped)
  - Test results (baseline vs post-patch)
  - Benchmark numbers (baseline vs after, with % change)
  - A brief explanation of methodology and caveats

Written to agent/data/report.md (and report.html for one-click sharing).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.state import AgentState, BenchmarkResult, Finding, TestResult

DATA_DIR = Path(__file__).resolve().parents[2] / "agent" / "data"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pct(before: float, after: float) -> str:
    if before == 0:
        return "n/a"
    change = (after - before) / before * 100
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.1f}%"


def _fmt(value: Optional[float], fmt: str, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{fmt.format(value)}{unit}"


def _test_badge(result: TestResult) -> str:
    if result["failed"] == 0 and result["errors"] == 0:
        return "✅ all passing"
    return f"⚠️ {result['failed']} failed, {result['errors']} errors"


def _impact_emoji(impact: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(impact, "⚪")


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def _build_markdown(state: AgentState) -> str:
    findings: list[Finding] = state.get("findings", [])
    proposals = state.get("proposals", [])
    decisions = state.get("decisions", [])
    applied = set(state.get("applied_patches", []))
    skipped = set(state.get("skipped_patches", []))
    baseline_tests: TestResult = state.get("baseline_tests", TestResult(passed=0, failed=0, errors=0, output=""))
    post_tests: TestResult = state.get("post_apply_tests", TestResult(passed=0, failed=0, errors=0, output=""))
    b: Optional[BenchmarkResult] = state.get("baseline_benchmark")
    a: Optional[BenchmarkResult] = state.get("after_benchmark")

    decisions_map = {d["finding_id"]: d for d in decisions}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# GreenCode Audit Report",
        "",
        f"*Generated {now} by the GreenCode LangGraph agent.*",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
    ]

    # Quick numbers
    n_findings = len(findings)
    n_applied = len(applied)
    if b and a:
        query_reduction = _pct(b["total_queries"], a["total_queries"])
        cpu_reduction = _pct(b["server_cpu_s"], a["server_cpu_s"])
        runtime_reduction = _pct(b["runtime_s"], a["runtime_s"])
        lines += [
            f"The audit detected **{n_findings} energy-inefficiency pattern(s)** in ShopLite.",
            f"**{n_applied}** fix(es) were approved, applied in an isolated git worktree, "
            "and verified by a behavioural test suite before measurement.",
            "",
            "| Metric | Before | After | Change |",
            "| --- | ---: | ---: | ---: |",
            f"| Total DB queries (1,000 req) | {b['total_queries']:,} | {a['total_queries']:,} | **{query_reduction}** |",
            f"| Server CPU time | {b['server_cpu_s']:.2f} s | {a['server_cpu_s']:.2f} s | **{cpu_reduction}** |",
            f"| Total runtime | {b['runtime_s']:.2f} s | {a['runtime_s']:.2f} s | **{runtime_reduction}** |",
        ]
        if b.get("energy_wh") and a.get("energy_wh"):
            lines.append(
                f"| Estimated energy (load phase) | {b['energy_wh']:.3f} Wh | "
                f"{a['energy_wh']:.3f} Wh | **{_pct(b['energy_wh'], a['energy_wh'])}** |"
            )
        if b.get("co2_g") and a.get("co2_g"):
            lines.append(
                f"| Estimated CO₂ (load phase) | {b['co2_g']:.3f} g | "
                f"{a['co2_g']:.3f} g | **{_pct(b['co2_g'], a['co2_g'])}** |"
            )
    else:
        lines.append(
            f"The audit detected **{n_findings} energy-inefficiency pattern(s)** in ShopLite. "
            f"**{n_applied}** fix(es) approved and applied.  "
            "Benchmark comparison not available (run the Measure node to populate)."
        )

    lines += [
        "",
        "---",
        "",
        "## 1 · Findings",
        "",
    ]

    pattern_labels = {
        "n+1_query": "N+1 Query",
        "polling_loop": "Polling Loop",
        "repeated_recomputation": "Repeated Recomputation",
    }

    for i, finding in enumerate(findings, 1):
        decision = decisions_map.get(finding["id"])
        status = "—"
        if finding["id"] in applied:
            status = "✅ Applied"
        elif finding["id"] in skipped:
            reason = decision["note"] if decision and decision["note"] else "rejected or no patch"
            status = f"⏭ Skipped ({reason})"
        elif decision and decision["approved"]:
            status = "✓ Approved (not yet applied)"

        lines += [
            f"### Finding {i}: {pattern_labels.get(finding['pattern'], finding['pattern'])}",
            "",
            f"| | |",
            f"| --- | --- |",
            f"| **ID** | `{finding['id']}` |",
            f"| **File** | `{finding['file']}` line {finding['line']} |",
            f"| **Impact** | {_impact_emoji(finding['energy_impact'])} {finding['energy_impact'].capitalize()} |",
            f"| **Status** | {status} |",
            "",
            f"**Problem:** {finding['description']}",
            "",
            f"**Suggested fix:** {finding['suggestion']}",
            "",
        ]

    lines += [
        "---",
        "",
        "## 2 · Test Results",
        "",
        "Behavioural tests were written *before* any code was changed to lock in the "
        "observable contract of each affected endpoint.  The same suite was re-run "
        "against the patched worktree to detect regressions.",
        "",
        "| Phase | Passed | Failed | Errors | Verdict |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Baseline (original code) | {baseline_tests['passed']} | {baseline_tests['failed']} | "
        f"{baseline_tests['errors']} | {_test_badge(baseline_tests)} |",
        f"| Post-patch (worktree) | {post_tests['passed']} | {post_tests['failed']} | "
        f"{post_tests['errors']} | {_test_badge(post_tests)} |",
        "",
    ]

    if b:
        lines += [
            "---",
            "",
            "## 3 · Benchmark Details",
            "",
            "All measurements use `benchmark/loadtest.py`: 1,000 requests (round-robin across "
            "`/users/summary`, `/products/report`, `/users/<id>`), median of 3 runs, "
            "with a 10-second idle window to capture background activity.",
            "",
            "| Metric | Baseline | After | Change |",
            "| --- | ---: | ---: | ---: |",
            f"| Total DB queries | {b['total_queries']:,} | "
            + (_fmt(a["total_queries"] if a else None, "{:,.0f}") + " | " +
               (_pct(b["total_queries"], a["total_queries"]) if a else "—") if a else "— | —") + " |",
            f"| Idle DB queries (10 s) | {b['idle_queries']:,} | "
            + (_fmt(a["idle_queries"] if a else None, "{:,.0f}") + " | " +
               (_pct(b["idle_queries"], a["idle_queries"]) if a else "—") if a else "— | —") + " |",
            f"| Server CPU time | {b['server_cpu_s']:.2f} s | "
            + (_fmt(a["server_cpu_s"] if a else None, "{:.2f}", " s") + " | " +
               (_pct(b["server_cpu_s"], a["server_cpu_s"]) if a else "—") if a else "— | —") + " |",
            f"| Total runtime | {b['runtime_s']:.2f} s | "
            + (_fmt(a["runtime_s"] if a else None, "{:.2f}", " s") + " | " +
               (_pct(b["runtime_s"], a["runtime_s"]) if a else "—") if a else "— | —") + " |",
        ]
        if b.get("energy_wh"):
            lines.append(
                f"| Estimated energy† | {b['energy_wh']:.3f} Wh | "
                + (_fmt(a["energy_wh"] if a else None, "{:.3f}", " Wh") + " | " +
                   (_pct(b["energy_wh"], a["energy_wh"]) if a and a.get("energy_wh") else "—") if a else "— | —") + " |"
            )
        lines += [
            "",
            "> † Energy and CO₂ are **estimates** from codecarbon in offline mode: "
            "CPU load × typical chip power + RAM, for the whole machine, not only ShopLite.  "
            "Runtime and CPU time are the primary hard numbers; treat energy figures as directional proxies.",
            "",
        ]

    lines += [
        "---",
        "",
        "## 4 · How Bob Helped",
        "",
        "Bob ([IBM Bob](https://www.ibm.com/products/bob)) was used at every stage of building this system:",
        "",
        "| Stage | Bob's role |",
        "| --- | --- |",
        "| Architecture | Designed the LangGraph graph, state schema, and node contracts |",
        "| Detect patterns | Wrote the AST + regex detectors for N+1, polling, and recomputation |",
        "| Test generation | Authored the full behavioural test suite in `agent/tests/` |",
        "| Patch authoring | Wrote the deterministic patch functions in `agent/nodes/apply.py` |",
        "| Configuration | Created the `Green Code Auditor` custom mode and project rules |",
        "| Report | Generated this document from structured state data |",
        "",
        "The LangGraph agent is the **runtime engine** that orchestrates the workflow. "
        "Bob is the **build-time assistant** that designed and coded every component.",
        "",
        "---",
        "",
        "## 5 · Methodology & Caveats",
        "",
        "- All patches are applied in an isolated `git worktree` branch so the main "
        "working tree is never modified without explicit human approval.",
        "- Query counts are **exact** (instrumented via SQLite's `set_trace_callback`). "
        "Runtime, CPU time, and energy are **proxies** affected by system load.",
        "- The baseline was recorded once and reused.  For a rigorous comparison, "
        "re-run `benchmark/loadtest.py --label baseline` on the original code "
        "and `--label after` on the patched worktree from the same machine state.",
        "- Three patterns were targeted deliberately.  Real codebases may have "
        "different or additional inefficiencies.",
        "",
        "---",
        "",
        "*End of report.*",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# HTML builder  (self-contained, no external assets)
# ---------------------------------------------------------------------------

def _build_html(markdown_text: str) -> str:
    """Wrap the markdown in a minimal self-contained HTML page."""
    # Very light markdown → HTML: headings, tables, bold, code, paragraphs.
    import re

    html = markdown_text

    # Escape for safety before adding HTML
    html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Code spans
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    # Bold
    html = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", html)
    # Italic
    html = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html)
    # H1/H2/H3
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    # Horizontal rules
    html = re.sub(r"^---$", r"<hr>", html, flags=re.MULTILINE)

    # Tables
    def _convert_table(m: re.Match) -> str:
        lines = m.group(0).strip().splitlines()
        rows = []
        for i, line in enumerate(lines):
            if re.match(r"\|[\s\-:]+\|", line):
                continue  # separator row
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            tag = "th" if i == 0 else "td"
            row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            rows.append(f"<tr>{row}</tr>")
        return "<table>\n" + "\n".join(rows) + "\n</table>"

    html = re.sub(
        r"((?:\|.+\|\n)+)",
        _convert_table,
        html,
        flags=re.MULTILINE,
    )

    # Blockquotes
    html = re.sub(r"^&gt; (.+)$", r"<blockquote>\1</blockquote>", html, flags=re.MULTILINE)

    # Paragraphs / line-breaks: split on blank lines
    parts = re.split(r"\n{2,}", html)
    result_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith(("<h", "<hr", "<table", "<blockquote")):
            result_parts.append(part)
        else:
            result_parts.append(f"<p>{part.replace(chr(10), '<br>')}</p>")

    body = "\n".join(result_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GreenCode Audit Report</title>
<style>
  body {{
    font-family: -apple-system,"Segoe UI",system-ui,sans-serif;
    font-size: 15px;
    line-height: 1.65;
    color: #1f2328;
    background: #ffffff;
    max-width: 860px;
    margin: 40px auto;
    padding: 0 24px 60px;
  }}
  h1 {{ font-size: 1.8em; border-bottom: 2px solid #3b82d4; padding-bottom: 8px; }}
  h2 {{ font-size: 1.3em; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-top: 2em; }}
  h3 {{ font-size: 1.1em; margin-top: 1.6em; }}
  hr  {{ border: none; border-top: 1px solid #e5e7eb; margin: 32px 0; }}
  code {{
    background: #f7f8fa;
    border: 1px solid #e5e7eb;
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 0.88em;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 0.93em;
    margin: 1em 0;
  }}
  th, td {{
    border: 1px solid #e5e7eb;
    padding: 7px 12px;
    text-align: left;
  }}
  th {{ background: #f7f8fa; font-weight: 600; }}
  tr:nth-child(even) td {{ background: #fafafa; }}
  blockquote {{
    border-left: 3px solid #3b82d4;
    margin: 16px 0;
    padding: 8px 16px;
    color: #57606a;
    background: #f7f8fa;
  }}
  em {{ color: #57606a; }}
  .footer {{
    margin-top: 60px;
    padding-top: 16px;
    border-top: 1px solid #e5e7eb;
    text-align: center;
    font-size: 12px;
    color: #57606a;
  }}
</style>
</head>
<body>
{body}
<div class="footer">Made with IBM Bob</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def report(state: AgentState) -> AgentState:
    """Write report.md and report.html to agent/data/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    md_text = _build_markdown(state)
    md_path = DATA_DIR / "report.md"
    html_path = DATA_DIR / "report.html"

    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(_build_html(md_text), encoding="utf-8")

    print(f"[report] Written → {md_path}")
    print(f"[report] Written → {html_path}")

    return {**state, "report_path": str(md_path)}
