from __future__ import annotations

from pathlib import Path

from loop_engineering_agent import JsonlTraceStore
from loop_engineering_agent.cli import analyze_traces, run_demo


def test_run_demo_can_persist_trace_for_later_analysis(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path / "runs.jsonl")

    result = run_demo("Trace this run", trace_store=store)
    analysis = analyze_traces(store)

    assert result["passed"] is True
    assert store.count() == 1
    assert analysis["trace_count"] == 1
    assert any(item["target"] == "system_prompt" for item in analysis["hill_climb_suggestions"])
