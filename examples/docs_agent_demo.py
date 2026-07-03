from __future__ import annotations

from dataclasses import asdict
from pprint import pprint

from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    HillClimber,
    HumanApprovalGate,
    ScriptedModel,
    Tool,
    VerificationLoop,
)


DOC_STORE = {"docs/agent.md": "Existing docs explain basic agents only."}


def read_doc(path: str) -> str:
    return DOC_STORE[path]


def write_doc(path: str, content: str) -> str:
    DOC_STORE[path] = content
    return f"wrote {path}"


def main() -> None:
    approval_gate = HumanApprovalGate(policy={"write_doc": "documentation write"})
    approval_gate.approve("write_doc")

    model = ScriptedModel(
        [
            {"tool": "read_doc", "args": {"path": "docs/agent.md"}},
            {"final": "Add a verification loop paragraph."},
            {"tool": "write_doc", "args": {"path": "docs/agent.md", "content": "Agent loop + verification loop + event-driven loop + hill-climbing loop."}},
            {"final": "Updated docs with verification loop, event-driven loop, and hill-climbing loop."},
        ]
    )

    agent = AgentLoop(
        model=model,
        tools=[
            Tool("read_doc", read_doc, description="Read a doc file"),
            Tool("write_doc", write_doc, description="Write a doc file", approval_gate=approval_gate),
        ],
        config=AgentConfig(system_prompt="You are a docs improvement agent."),
    )
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(
            required_phrases=["verification loop", "event-driven loop", "hill-climbing loop"]
        ),
        max_attempts=2,
    )
    app = EventDrivenLoop(verification_loop=verified)
    result = app.handle(Event(kind="slack.message", payload={"text": "Improve the agent docs"}))
    suggestions = HillClimber(min_failure_count=1).analyze(app.traces)

    pprint(
        {
            "result": result.output,
            "passed": result.passed,
            "attempts": result.attempts,
            "trace": asdict(result.trace),
            "hill_climb_suggestions": [asdict(item) for item in suggestions],
        }
    )


if __name__ == "__main__":
    main()
