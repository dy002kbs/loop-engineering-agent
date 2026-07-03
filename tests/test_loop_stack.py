from __future__ import annotations

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


def test_agent_loop_calls_tools_until_final_answer_and_records_trace() -> None:
    calls: list[str] = []

    def read_doc(path: str) -> str:
        calls.append(path)
        return "Current docs mention agents but not loop engineering."

    model = ScriptedModel(
        [
            {"tool": "read_doc", "args": {"path": "docs/agent.md"}},
            {"final": "Add a Loop Engineering section after the agent overview."},
        ]
    )
    agent = AgentLoop(
        model=model,
        tools=[Tool("read_doc", read_doc, description="Read a documentation file")],
        config=AgentConfig(system_prompt="You improve docs."),
    )

    result = agent.run("Improve docs with loop engineering context")

    assert result.output == "Add a Loop Engineering section after the agent overview."
    assert calls == ["docs/agent.md"]
    assert result.trace.task == "Improve docs with loop engineering context"
    assert result.trace.steps[0].tool_name == "read_doc"
    assert result.trace.steps[0].observation == "Current docs mention agents but not loop engineering."
    assert result.trace.final_output == result.output


def test_verification_loop_retries_with_grader_feedback_until_rubric_passes() -> None:
    model = ScriptedModel(
        [
            {"final": "Ship the draft."},
            {"final": "Ship the draft with verification loop, event-driven loop, and hill-climbing loop."},
        ]
    )
    agent = AgentLoop(model=model, tools=[], config=AgentConfig(system_prompt="You draft agent plans."))
    grader = DeterministicRubricGrader(
        required_phrases=["verification loop", "event-driven loop", "hill-climbing loop"],
        max_length=140,
    )
    loop = VerificationLoop(agent=agent, grader=grader, max_attempts=3)

    result = loop.run("Draft a loop engineering plan")

    assert result.passed is True
    assert result.attempts == 2
    assert result.output == "Ship the draft with verification loop, event-driven loop, and hill-climbing loop."
    assert result.trace.verification_results[0].passed is False
    assert "Missing required phrases" in result.trace.verification_results[0].feedback
    assert result.trace.verification_results[-1].passed is True


def test_event_driven_loop_routes_events_to_the_verified_agent() -> None:
    model = ScriptedModel([{"final": "Use an event-driven loop for new docs requests."}])
    agent = AgentLoop(model=model, tools=[], config=AgentConfig(system_prompt="You handle events."))
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(required_phrases=["event-driven loop"]),
        max_attempts=1,
    )
    app_loop = EventDrivenLoop(verification_loop=verified)

    result = app_loop.handle(Event(kind="slack.message", payload={"text": "Please improve docs"}))

    assert result.output == "Use an event-driven loop for new docs requests."
    assert result.passed is True
    assert app_loop.traces[0].trigger.kind == "slack.message"
    assert app_loop.traces[0].task == "Please improve docs"


def test_hill_climber_turns_repeated_trace_failures_into_config_updates() -> None:
    model = ScriptedModel(
        [
            {"final": "Too vague."},
            {"final": "Still vague."},
        ]
    )
    config = AgentConfig(system_prompt="Draft quickly.", rubric=["Mention verification loop"])
    agent = AgentLoop(model=model, tools=[], config=config)
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(required_phrases=["verification loop"]),
        max_attempts=2,
    )
    failed = verified.run("Need a reliable agent design")

    climber = HillClimber(min_failure_count=1)
    suggestions = climber.analyze([failed.trace])
    updated = climber.apply(config, suggestions)

    assert failed.passed is False
    assert suggestions
    assert suggestions[0].target in {"system_prompt", "rubric"}
    assert "verification loop" in updated.system_prompt.lower() or "verification loop" in " ".join(updated.rubric).lower()
    assert updated != config


def test_human_approval_gate_blocks_sensitive_tool_until_approved() -> None:
    gate = HumanApprovalGate(policy={"git_push": "sensitive"})
    tool = Tool("git_push", lambda branch: f"pushed {branch}", description="Push code", approval_gate=gate)

    blocked = tool.invoke({"branch": "main"})
    assert blocked.approved is False
    assert "requires human approval" in blocked.observation

    gate.approve("git_push")
    approved = tool.invoke({"branch": "main"})
    assert approved.approved is True
    assert approved.observation == "pushed main"
