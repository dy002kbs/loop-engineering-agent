from __future__ import annotations

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


def build_loop() -> EventDrivenLoop:
    model = ScriptedModel(
        [
            {"final": "Handled webhook with verification loop, event-driven loop, and hill-climbing loop."},
            {"final": "Handled cron with verification loop, event-driven loop, and hill-climbing loop."},
        ]
    )
    agent = AgentLoop(model=model, tools=[], config=AgentConfig(system_prompt="Handle API-triggered tasks."))
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(
            required_phrases=["verification loop", "event-driven loop", "hill-climbing loop"]
        ),
        max_attempts=1,
    )
    return EventDrivenLoop(verification_loop=verified)


app = create_app(
    event_loop=build_loop(),
    trace_store=JsonlTraceStore(".traces/server-runs.jsonl"),
    cron_jobs=[CronJob(name="nightly-docs", event_kind="cron.nightly", payload={"text": "Nightly docs check"})],
)
