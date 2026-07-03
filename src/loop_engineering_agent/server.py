from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .core import Event, EventDrivenLoop, VerifiedRun
from .persistence import JsonlTraceStore, SQLiteTraceStore, trace_to_dict


@dataclass(frozen=True)
class CronJob:
    """A named cron-style trigger that can be invoked by the API server."""

    name: str
    event_kind: str
    payload: dict[str, Any]


TraceStore = JsonlTraceStore | SQLiteTraceStore


def verified_run_to_dict(result: VerifiedRun) -> dict[str, Any]:
    return {
        "output": result.output,
        "passed": result.passed,
        "attempts": result.attempts,
        "trigger": (
            {"kind": result.trace.trigger.kind, "payload": dict(result.trace.trigger.payload)}
            if result.trace.trigger
            else None
        ),
        "trace": trace_to_dict(result.trace),
    }


def create_app(
    *,
    event_loop: EventDrivenLoop,
    trace_store: TraceStore | None = None,
    cron_jobs: Iterable[CronJob] = (),
):
    """Create a FastAPI app for webhook and cron-style event triggers."""

    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "Install the server extra to use create_app: python -m pip install -e .[server]"
        ) from exc

    cron_by_name = {job.name: job for job in cron_jobs}
    app = FastAPI(title="Loop Engineering Agent", version="0.1.0")

    def run_event(event: Event) -> dict[str, Any]:
        result = event_loop.handle(event)
        if trace_store is not None:
            trace_store.append(result.trace)
        return verified_run_to_dict(result)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "cron_jobs": sorted(cron_by_name)}

    @app.post("/webhooks/{event_kind}")
    def webhook(event_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        return run_event(Event(kind=event_kind, payload=payload))

    @app.post("/cron/{job_name}/run")
    def run_cron(job_name: str) -> dict[str, Any]:
        job = cron_by_name.get(job_name)
        if not job:
            raise HTTPException(status_code=404, detail=f"Unknown cron job: {job_name}")
        return run_event(Event(kind=job.event_kind, payload=job.payload))

    return app
