from __future__ import annotations

from pathlib import Path

from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    HillClimber,
    JsonlTraceStore,
    ScriptedModel,
    SQLiteTraceStore,
    VerificationLoop,
    trace_from_dict,
    trace_to_dict,
)


def _failed_trace():
    model = ScriptedModel([{"final": "Too vague."}])
    agent = AgentLoop(model=model, tools=[], config=AgentConfig(system_prompt="Draft carefully."))
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(required_phrases=["verification loop"]),
        max_attempts=1,
    )
    app = EventDrivenLoop(verification_loop=verified)
    result = app.handle(Event(kind="webhook.docs", payload={"text": "Improve docs"}))
    return result.trace


def test_trace_serializes_to_json_safe_dict_and_back() -> None:
    trace = _failed_trace()

    data = trace_to_dict(trace)
    restored = trace_from_dict(data)

    assert data["task"] == "Improve docs"
    assert data["trigger"]["kind"] == "webhook.docs"
    assert data["verification_results"][0]["passed"] is False
    assert restored.task == trace.task
    assert restored.trigger is not None
    assert restored.trigger.kind == "webhook.docs"
    assert restored.verification_results[0].feedback.startswith("Missing required phrases")


def test_jsonl_trace_store_appends_and_reads_traces(tmp_path: Path) -> None:
    trace = _failed_trace()
    store = JsonlTraceStore(tmp_path / "runs.jsonl")

    store.append(trace)
    store.append(trace)
    loaded = list(store.list())

    assert store.count() == 2
    assert [item.task for item in loaded] == ["Improve docs", "Improve docs"]
    assert loaded[0].trigger is not None
    assert loaded[0].trigger.kind == "webhook.docs"
    assert HillClimber(min_failure_count=1).analyze(loaded)


def test_sqlite_trace_store_persists_metadata_and_round_trips(tmp_path: Path) -> None:
    trace = _failed_trace()
    store = SQLiteTraceStore(tmp_path / "traces.sqlite3")

    first_id = store.append(trace)
    second_id = store.append(trace)
    loaded = list(store.list(trigger_kind="webhook.docs"))

    assert first_id == 1
    assert second_id == 2
    assert store.count() == 2
    assert store.count(trigger_kind="webhook.docs") == 2
    assert loaded[0].task == "Improve docs"
    assert loaded[0].verification_results[0].passed is False
