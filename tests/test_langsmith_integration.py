from __future__ import annotations

import json
from pathlib import Path

from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    JsonlTraceStore,
    LangSmithTraceExporter,
    LangSmithTraceImporter,
    ScriptedModel,
    Tool,
    VerificationLoop,
    langsmith_run_payloads,
)
from loop_engineering_agent.cli import export_langsmith_payloads


def _trace():
    model = ScriptedModel(
        [
            {"tool": "read", "args": {"path": "README.md"}},
            {"final": "Plan with verification loop."},
        ]
    )
    tool = lambda path: f"read {path}"
    agent = AgentLoop(
        model=model,
        tools=[Tool("read", tool, description="Read docs")],
        config=AgentConfig(system_prompt="Handle docs."),
    )
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(required_phrases=["verification loop"]),
        max_attempts=1,
    )
    app = EventDrivenLoop(verification_loop=verified)
    return app.handle(Event(kind="webhook.docs", payload={"text": "Improve docs"})).trace


class _FakeLangSmithClient:
    def __init__(self, runs=None):
        self.created_runs = []
        self._runs = runs or []

    def create_run(self, **kwargs):
        self.created_runs.append(kwargs)
        return kwargs.get("id")

    def list_runs(self, **kwargs):
        self.list_kwargs = kwargs
        return list(self._runs)


def test_langsmith_run_payloads_include_root_children_and_serialized_trace() -> None:
    trace = _trace()

    payloads = langsmith_run_payloads(trace, project_name="loop-tests", root_run_id="root-id")

    assert payloads[0]["id"] == "root-id"
    assert payloads[0]["project_name"] == "loop-tests"
    assert payloads[0]["run_type"] == "chain"
    assert payloads[0]["inputs"]["task"] == "Improve docs"
    assert payloads[0]["outputs"]["final_output"] == "Plan with verification loop."
    assert payloads[0]["extra"]["loop_engineering_trace"]["trigger"]["kind"] == "webhook.docs"
    assert any(item["run_type"] == "tool" and item["parent_run_id"] == "root-id" for item in payloads[1:])
    assert any(
        item["run_type"] == "chain"
        and item["name"].startswith("verification:")
        and item["parent_run_id"] == "root-id"
        for item in payloads[1:]
    )


def test_langsmith_exporter_calls_create_run_for_payloads() -> None:
    client = _FakeLangSmithClient()
    exporter = LangSmithTraceExporter(client=client, project_name="loop-tests")

    result = exporter.export_trace(_trace(), root_run_id="root-id")

    assert result.root_run_id == "root-id"
    assert result.run_count == len(client.created_runs)
    assert client.created_runs[0]["id"] == "root-id"
    assert all(run["project_name"] == "loop-tests" for run in client.created_runs)


def test_langsmith_importer_round_trips_trace_from_run_extra() -> None:
    original = _trace()
    root_payload = langsmith_run_payloads(original, project_name="loop-tests", root_run_id="root-id")[0]
    client = _FakeLangSmithClient(runs=[root_payload])
    importer = LangSmithTraceImporter(client=client)

    traces = list(importer.list_traces(project_name="loop-tests", limit=5))

    assert client.list_kwargs == {"project_name": "loop-tests", "limit": 5, "run_type": "chain"}
    assert len(traces) == 1
    assert traces[0].task == "Improve docs"
    assert traces[0].trigger is not None
    assert traces[0].trigger.kind == "webhook.docs"
    assert traces[0].verification_results[0].passed is True


def test_cli_langsmith_dry_run_export_writes_payload_jsonl(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path / "runs.jsonl")
    store.append(_trace())
    out_path = tmp_path / "langsmith-payloads.jsonl"

    summary = export_langsmith_payloads(store, project_name="loop-tests", dry_run_jsonl=out_path)

    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert summary["trace_count"] == 1
    assert summary["payload_count"] == len(lines)
    assert lines[0]["project_name"] == "loop-tests"
    assert lines[0]["extra"]["loop_engineering_trace"]["task"] == "Improve docs"
