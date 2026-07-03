from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .core import (
    AgentConfig,
    AgentLoop,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    HillClimber,
    ScriptedModel,
    Trace,
    VerificationLoop,
)
from .persistence import JsonlTraceStore, SQLiteTraceStore


class TraceStore(Protocol):
    def append(self, trace: Trace) -> int: ...
    def list(self, *, trigger_kind: str | None = None, limit: int | None = None): ...
    def count(self, *, trigger_kind: str | None = None) -> int: ...


def build_demo_loop() -> EventDrivenLoop:
    """Build an offline demo that exercises all four loops without an API key."""

    model = ScriptedModel(
        [
            {"final": "Draft a basic agent."},
            {
                "final": (
                    "Draft an agent with an agent loop, verification loop, "
                    "event-driven loop, hill-climbing loop, and human oversight."
                )
            },
        ]
    )
    config = AgentConfig(
        system_prompt="You convert work requests into reliable loop-engineered agent plans.",
        rubric=["Mention verification loop", "Mention event-driven loop", "Mention hill-climbing loop"],
    )
    agent = AgentLoop(model=model, tools=[], config=config)
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(
            required_phrases=["verification loop", "event-driven loop", "hill-climbing loop"]
        ),
        max_attempts=2,
    )
    return EventDrivenLoop(verification_loop=verified)


def run_demo(task: str, *, trace_store: TraceStore | None = None) -> dict:
    app_loop = build_demo_loop()
    result = app_loop.handle(Event(kind="cli.demo", payload={"text": task}))
    if trace_store is not None:
        trace_store.append(result.trace)
    suggestions = HillClimber(min_failure_count=1).analyze(app_loop.traces)
    return {
        "passed": result.passed,
        "attempts": result.attempts,
        "output": result.output,
        "trigger": asdict(result.trace.trigger) if result.trace.trigger else None,
        "verification_feedback": [asdict(item) for item in result.trace.verification_results],
        "hill_climb_suggestions": [asdict(item) for item in suggestions],
    }


def analyze_traces(trace_store: TraceStore) -> dict:
    traces = list(trace_store.list())
    suggestions = HillClimber(min_failure_count=1).analyze(traces)
    return {
        "trace_count": len(traces),
        "hill_climb_suggestions": [asdict(item) for item in suggestions],
    }


def _trace_store_from_args(args: argparse.Namespace) -> TraceStore | None:
    if args.trace_jsonl and args.trace_sqlite:
        raise SystemExit("Choose only one of --trace-jsonl or --trace-sqlite.")
    if args.trace_jsonl:
        return JsonlTraceStore(Path(args.trace_jsonl))
    if args.trace_sqlite:
        return SQLiteTraceStore(Path(args.trace_sqlite))
    return None


def _analysis_store_from_args(args: argparse.Namespace) -> TraceStore | None:
    if args.analyze_jsonl and args.analyze_sqlite:
        raise SystemExit("Choose only one of --analyze-jsonl or --analyze-sqlite.")
    if args.analyze_jsonl:
        return JsonlTraceStore(Path(args.analyze_jsonl))
    if args.analyze_sqlite:
        return SQLiteTraceStore(Path(args.analyze_sqlite))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Loop Engineering Agent offline demo.")
    parser.add_argument("task", nargs="?", default="Turn loop engineering into an agent harness")
    parser.add_argument("--trace-jsonl", help="Append the run trace to a JSONL file.")
    parser.add_argument("--trace-sqlite", help="Append the run trace to a SQLite database.")
    parser.add_argument("--analyze-jsonl", help="Analyze traces from a JSONL file instead of running the demo.")
    parser.add_argument("--analyze-sqlite", help="Analyze traces from a SQLite database instead of running the demo.")
    args = parser.parse_args(argv)

    analysis_store = _analysis_store_from_args(args)
    if analysis_store is not None:
        print(json.dumps(analyze_traces(analysis_store), ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(run_demo(args.task, trace_store=_trace_store_from_args(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
