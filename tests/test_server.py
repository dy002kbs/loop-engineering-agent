from __future__ import annotations

from fastapi.testclient import TestClient

from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    CronJob,
    DeterministicRubricGrader,
    EventDrivenLoop,
    JsonlTraceStore,
    ScriptedModel,
    VerificationLoop,
    create_app,
)


def _demo_loop() -> EventDrivenLoop:
    model = ScriptedModel(
        [
            {"final": "Webhook run with verification loop."},
            {"final": "Cron run with verification loop."},
        ]
    )
    agent = AgentLoop(model=model, tools=[], config=AgentConfig(system_prompt="Handle events."))
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(required_phrases=["verification loop"]),
        max_attempts=1,
    )
    return EventDrivenLoop(verification_loop=verified)


def test_fastapi_webhook_endpoint_runs_event_loop_and_stores_trace(tmp_path) -> None:
    store = JsonlTraceStore(tmp_path / "runs.jsonl")
    app = create_app(event_loop=_demo_loop(), trace_store=store)
    client = TestClient(app)

    response = client.post("/webhooks/slack.message", json={"text": "Improve docs"})

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["output"] == "Webhook run with verification loop."
    assert body["trace"]["trigger"]["kind"] == "slack.message"
    assert store.count() == 1


def test_fastapi_cron_endpoint_runs_named_cron_job(tmp_path) -> None:
    store = JsonlTraceStore(tmp_path / "runs.jsonl")
    app = create_app(
        event_loop=_demo_loop(),
        trace_store=store,
        cron_jobs=[CronJob(name="nightly-docs", event_kind="cron.nightly", payload={"text": "Nightly docs"})],
    )
    client = TestClient(app)

    response = client.post("/cron/nightly-docs/run")

    assert response.status_code == 200
    body = response.json()
    assert body["trigger"]["kind"] == "cron.nightly"
    assert body["output"] == "Webhook run with verification loop."
    assert store.count(trigger_kind="cron.nightly") == 1


def test_fastapi_health_endpoint_reports_registered_cron_jobs() -> None:
    app = create_app(
        event_loop=_demo_loop(),
        cron_jobs=[CronJob(name="heartbeat", event_kind="cron.heartbeat", payload={"text": "Ping"})],
    )
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "cron_jobs": ["heartbeat"]}
