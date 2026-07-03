from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .core import Event, StepTrace, Trace, VerificationResult

SCHEMA_VERSION = 1


def _json_safe(value: Any) -> Any:
    """Convert trace values into JSON-safe primitives."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    return str(value)


def trace_to_dict(trace: Trace) -> dict[str, Any]:
    """Serialize a Trace to a JSON-safe dictionary."""

    return {
        "schema_version": SCHEMA_VERSION,
        "task": trace.task,
        "system_prompt": trace.system_prompt,
        "steps": [
            {
                "tool_name": step.tool_name,
                "args": _json_safe(dict(step.args)),
                "observation": _json_safe(step.observation),
                "approved": step.approved,
                "error": step.error,
            }
            for step in trace.steps
        ],
        "verification_results": [
            {
                "passed": item.passed,
                "feedback": item.feedback,
                "details": _json_safe(dict(item.details)),
            }
            for item in trace.verification_results
        ],
        "final_output": trace.final_output,
        "trigger": (
            {"kind": trace.trigger.kind, "payload": _json_safe(dict(trace.trigger.payload))}
            if trace.trigger
            else None
        ),
        "feedback_history": list(trace.feedback_history),
    }


def trace_from_dict(data: dict[str, Any]) -> Trace:
    """Rehydrate a Trace from trace_to_dict output."""

    trigger_data = data.get("trigger")
    trigger = None
    if trigger_data:
        trigger = Event(kind=str(trigger_data["kind"]), payload=dict(trigger_data.get("payload") or {}))

    trace = Trace(
        task=str(data.get("task", "")),
        system_prompt=str(data.get("system_prompt", "")),
        steps=[
            StepTrace(
                tool_name=str(step.get("tool_name", "")),
                args=dict(step.get("args") or {}),
                observation=step.get("observation"),
                approved=bool(step.get("approved", True)),
                error=step.get("error"),
            )
            for step in data.get("steps", [])
        ],
        verification_results=[
            VerificationResult(
                passed=bool(item.get("passed", False)),
                feedback=str(item.get("feedback", "")),
                details=dict(item.get("details") or {}),
            )
            for item in data.get("verification_results", [])
        ],
        final_output=data.get("final_output"),
        trigger=trigger,
        feedback_history=[str(item) for item in data.get("feedback_history", [])],
    )
    return trace


class JsonlTraceStore:
    """Append-only JSONL trace store for lightweight local hill climbing."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, trace: Trace) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trace": trace_to_dict(trace),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return self.count()

    def list(self, *, trigger_kind: str | None = None, limit: int | None = None) -> Iterable[Trace]:
        if not self.path.exists():
            return []

        traces: list[Trace] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                trace = trace_from_dict(record["trace"])
                if trigger_kind and (not trace.trigger or trace.trigger.kind != trigger_kind):
                    continue
                traces.append(trace)

        if limit is not None:
            traces = traces[-limit:]
        return traces

    def count(self, *, trigger_kind: str | None = None) -> int:
        return sum(1 for _ in self.list(trigger_kind=trigger_kind))


class SQLiteTraceStore:
    """SQLite trace store with metadata columns and full JSON payloads."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    task TEXT NOT NULL,
                    trigger_kind TEXT,
                    passed INTEGER,
                    trace_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_trigger_kind ON traces(trigger_kind)")

    def append(self, trace: Trace) -> int:
        trace_dict = trace_to_dict(trace)
        trigger_kind = trace.trigger.kind if trace.trigger else None
        passed = None
        if trace.verification_results:
            passed = 1 if trace.verification_results[-1].passed else 0
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO traces(created_at, task, trigger_kind, passed, trace_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    trace.task,
                    trigger_kind,
                    passed,
                    json.dumps(trace_dict, ensure_ascii=False, sort_keys=True),
                ),
            )
            return int(cursor.lastrowid)

    def list(self, *, trigger_kind: str | None = None, limit: int | None = None) -> Iterable[Trace]:
        sql = "SELECT trace_json FROM traces"
        params: list[Any] = []
        if trigger_kind:
            sql += " WHERE trigger_kind = ?"
            params.append(trigger_kind)
        sql += " ORDER BY id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [trace_from_dict(json.loads(row[0])) for row in rows]

    def count(self, *, trigger_kind: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM traces"
        params: list[Any] = []
        if trigger_kind:
            sql += " WHERE trigger_kind = ?"
            params.append(trigger_kind)
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row[0])
