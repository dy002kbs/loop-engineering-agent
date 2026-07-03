from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import Trace
from .persistence import trace_from_dict, trace_to_dict


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _child_id(root_run_id: str, kind: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"loop-engineering-agent/{root_run_id}/{kind}/{index}"))


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def langsmith_run_payloads(
    trace: Trace,
    *,
    project_name: str,
    root_run_id: str | None = None,
    run_name: str = "loop-engineering-agent.run",
) -> list[dict[str, Any]]:
    """Convert a local Trace into LangSmith create_run payloads.

    The first payload is the root chain run. Tool calls and verification results
    are exported as child runs so LangSmith can show the loop structure.
    """

    root_id = root_run_id or str(uuid.uuid4())
    trace_dict = trace_to_dict(trace)
    passed = trace.verification_results[-1].passed if trace.verification_results else None
    timestamp = _now_iso()

    payloads: list[dict[str, Any]] = [
        {
            "id": root_id,
            "name": run_name,
            "run_type": "chain",
            "project_name": project_name,
            "inputs": {
                "task": trace.task,
                "system_prompt": trace.system_prompt,
                "trigger": trace_dict.get("trigger"),
            },
            "outputs": {"final_output": trace.final_output, "passed": passed},
            "extra": {
                "loop_engineering_trace": trace_dict,
                "loop_engineering_schema_version": trace_dict.get("schema_version"),
            },
            "start_time": timestamp,
            "end_time": timestamp,
        }
    ]

    for index, step in enumerate(trace.steps):
        payloads.append(
            {
                "id": _child_id(root_id, "tool", index),
                "name": f"tool:{step.tool_name}",
                "run_type": "tool",
                "project_name": project_name,
                "parent_run_id": root_id,
                "inputs": {"args": dict(step.args)},
                "outputs": {
                    "observation": step.observation,
                    "approved": step.approved,
                    "error": step.error,
                },
                "extra": {"loop_engineering_step_index": index},
                "start_time": timestamp,
                "end_time": timestamp,
            }
        )

    for index, result in enumerate(trace.verification_results):
        payloads.append(
            {
                "id": _child_id(root_id, "verification", index),
                "name": f"verification:{index}",
                "run_type": "chain",
                "project_name": project_name,
                "parent_run_id": root_id,
                "inputs": {"output": trace.final_output},
                "outputs": {
                    "passed": result.passed,
                    "feedback": result.feedback,
                    "details": dict(result.details),
                },
                "extra": {"loop_engineering_verification_index": index},
                "start_time": timestamp,
                "end_time": timestamp,
            }
        )

    return payloads


@dataclass(frozen=True)
class LangSmithExportResult:
    root_run_id: str
    project_name: str
    run_count: int


class LangSmithTraceExporter:
    """Export local traces to LangSmith using an injectable client."""

    def __init__(self, *, client: Any, project_name: str = "loop-engineering-agent"):
        self.client = client
        self.project_name = project_name

    @classmethod
    def from_environment(cls, *, project_name: str = "loop-engineering-agent") -> "LangSmithTraceExporter":
        try:
            from langsmith import Client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "Install the langsmith extra to use LangSmithTraceExporter: "
                "python -m pip install -e .[langsmith]"
            ) from exc
        return cls(client=Client(), project_name=project_name)

    def export_trace(self, trace: Trace, *, root_run_id: str | None = None) -> LangSmithExportResult:
        payloads = langsmith_run_payloads(trace, project_name=self.project_name, root_run_id=root_run_id)
        for payload in payloads:
            self.client.create_run(**payload)
        return LangSmithExportResult(
            root_run_id=str(payloads[0]["id"]),
            project_name=self.project_name,
            run_count=len(payloads),
        )

    def export_traces(self, traces: Iterable[Trace]) -> list[LangSmithExportResult]:
        return [self.export_trace(trace) for trace in traces]


class LangSmithTraceImporter:
    """Import traces previously exported to LangSmith."""

    def __init__(self, *, client: Any):
        self.client = client

    @classmethod
    def from_environment(cls) -> "LangSmithTraceImporter":
        try:
            from langsmith import Client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "Install the langsmith extra to use LangSmithTraceImporter: "
                "python -m pip install -e .[langsmith]"
            ) from exc
        return cls(client=Client())

    def list_traces(self, *, project_name: str, limit: int = 100) -> Iterable[Trace]:
        runs = self.client.list_runs(project_name=project_name, limit=limit, run_type="chain")
        traces: list[Trace] = []
        for run in runs:
            trace_data = self._extract_trace_data(run)
            if trace_data:
                traces.append(trace_from_dict(trace_data))
        return traces

    def _extract_trace_data(self, run: Any) -> dict[str, Any] | None:
        extra = _get(run, "extra", default={}) or {}
        outputs = _get(run, "outputs", default={}) or {}
        trace_data = _get(extra, "loop_engineering_trace") or _get(outputs, "loop_engineering_trace") or _get(outputs, "trace")
        if isinstance(trace_data, Mapping):
            return dict(trace_data)
        if isinstance(trace_data, str):
            parsed = json.loads(trace_data)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        return None


def write_langsmith_payloads_jsonl(
    path: str | Path,
    traces: Iterable[Trace],
    *,
    project_name: str,
) -> int:
    """Write LangSmith create_run payloads to JSONL for offline inspection."""

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for trace in traces:
            for payload in langsmith_run_payloads(trace, project_name=project_name):
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
                count += 1
    return count
