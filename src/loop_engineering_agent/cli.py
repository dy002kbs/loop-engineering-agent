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
from .langsmith import LangSmithTraceExporter, LangSmithTraceImporter, write_langsmith_payloads_jsonl
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


def export_langsmith_payloads(
    trace_store: TraceStore,
    *,
    project_name: str,
    dry_run_jsonl: str | Path | None = None,
    exporter: LangSmithTraceExporter | None = None,
    limit: int | None = None,
) -> dict:
    """Export local traces to LangSmith or write LangSmith payloads to JSONL."""

    traces = list(trace_store.list(limit=limit))
    if dry_run_jsonl:
        payload_count = write_langsmith_payloads_jsonl(dry_run_jsonl, traces, project_name=project_name)
        return {
            "mode": "dry-run-jsonl",
            "project_name": project_name,
            "trace_count": len(traces),
            "payload_count": payload_count,
            "path": str(dry_run_jsonl),
        }

    exporter = exporter or LangSmithTraceExporter.from_environment(project_name=project_name)
    results = exporter.export_traces(traces)
    return {
        "mode": "langsmith",
        "project_name": project_name,
        "trace_count": len(traces),
        "payload_count": sum(item.run_count for item in results),
        "root_run_ids": [item.root_run_id for item in results],
    }


def import_langsmith_traces(
    trace_store: TraceStore,
    *,
    project_name: str,
    importer: LangSmithTraceImporter | None = None,
    limit: int = 100,
) -> dict:
    """Import LangSmith runs that contain loop_engineering_trace metadata."""

    importer = importer or LangSmithTraceImporter.from_environment()
    traces = list(importer.list_traces(project_name=project_name, limit=limit))
    for trace in traces:
        trace_store.append(trace)
    return {"project_name": project_name, "imported_trace_count": len(traces)}


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


def _langsmith_export_store_from_args(args: argparse.Namespace) -> TraceStore | None:
    if args.export_langsmith_jsonl and args.export_langsmith_sqlite:
        raise SystemExit("Choose only one of --export-langsmith-jsonl or --export-langsmith-sqlite.")
    if args.export_langsmith_jsonl:
        return JsonlTraceStore(Path(args.export_langsmith_jsonl))
    if args.export_langsmith_sqlite:
        return SQLiteTraceStore(Path(args.export_langsmith_sqlite))
    return None


def _langsmith_import_store_from_args(args: argparse.Namespace) -> TraceStore | None:
    if args.import_langsmith_jsonl and args.import_langsmith_sqlite:
        raise SystemExit("Choose only one of --import-langsmith-jsonl or --import-langsmith-sqlite.")
    if args.import_langsmith_jsonl:
        return JsonlTraceStore(Path(args.import_langsmith_jsonl))
    if args.import_langsmith_sqlite:
        return SQLiteTraceStore(Path(args.import_langsmith_sqlite))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Loop Engineering Agent offline demo.")
    parser.add_argument("task", nargs="?", default="Turn loop engineering into an agent harness")
    parser.add_argument("--trace-jsonl", help="Append the run trace to a JSONL file.")
    parser.add_argument("--trace-sqlite", help="Append the run trace to a SQLite database.")
    parser.add_argument("--analyze-jsonl", help="Analyze traces from a JSONL file instead of running the demo.")
    parser.add_argument("--analyze-sqlite", help="Analyze traces from a SQLite database instead of running the demo.")
    parser.add_argument("--export-langsmith-jsonl", help="Read local JSONL traces and export them to LangSmith.")
    parser.add_argument("--export-langsmith-sqlite", help="Read local SQLite traces and export them to LangSmith.")
    parser.add_argument("--import-langsmith-jsonl", help="Import LangSmith traces into a local JSONL trace store.")
    parser.add_argument("--import-langsmith-sqlite", help="Import LangSmith traces into a local SQLite trace store.")
    parser.add_argument("--langsmith-project", default="loop-engineering-agent", help="LangSmith project name.")
    parser.add_argument("--langsmith-limit", type=int, default=100, help="Maximum traces/runs to export or import.")
    parser.add_argument(
        "--langsmith-dry-run-jsonl",
        help="Write LangSmith create_run payloads to JSONL instead of calling the LangSmith API.",
    )
    args = parser.parse_args(argv)

    langsmith_export_store = _langsmith_export_store_from_args(args)
    if langsmith_export_store is not None:
        print(
            json.dumps(
                export_langsmith_payloads(
                    langsmith_export_store,
                    project_name=args.langsmith_project,
                    dry_run_jsonl=args.langsmith_dry_run_jsonl,
                    limit=args.langsmith_limit,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    langsmith_import_store = _langsmith_import_store_from_args(args)
    if langsmith_import_store is not None:
        print(
            json.dumps(
                import_langsmith_traces(
                    langsmith_import_store,
                    project_name=args.langsmith_project,
                    limit=args.langsmith_limit,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    analysis_store = _analysis_store_from_args(args)
    if analysis_store is not None:
        print(json.dumps(analyze_traces(analysis_store), ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(run_demo(args.task, trace_store=_trace_store_from_args(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
