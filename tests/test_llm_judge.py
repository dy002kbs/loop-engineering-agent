from __future__ import annotations

from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    Event,
    LLMJudgeGrader,
    ScriptedModel,
    VerificationLoop,
)


class RecordingJudge:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        return self.response


def test_llm_judge_grader_parses_structured_judge_response() -> None:
    judge = RecordingJudge(
        {
            "passed": False,
            "feedback": "Needs a concrete verification loop.",
            "details": {"score": 0.35, "missing": ["verification loop"]},
        }
    )
    grader = LLMJudgeGrader(judge=judge, rubric=["Mention verification loop"])

    result = grader.grade(
        task="Draft a reliable agent plan",
        output="Draft a simple agent.",
        trace=AgentLoop(
            model=ScriptedModel([{"final": "unused"}]),
            tools=[],
            config=AgentConfig(system_prompt="test"),
        ).run("seed").trace,
    )

    assert result.passed is False
    assert result.feedback == "Needs a concrete verification loop."
    assert result.details["score"] == 0.35
    assert judge.calls[0]["rubric"] == ["Mention verification loop"]
    assert judge.calls[0]["task"] == "Draft a reliable agent plan"
    assert judge.calls[0]["output"] == "Draft a simple agent."


def test_llm_judge_grader_can_drive_verification_retry() -> None:
    judge = RecordingJudge('{"passed": true, "feedback": "looks good", "details": {"score": 0.9}}')
    agent = AgentLoop(
        model=ScriptedModel([{"final": "Plan with verification loop."}]),
        tools=[],
        config=AgentConfig(system_prompt="Draft agent plans."),
    )
    loop = VerificationLoop(agent=agent, grader=LLMJudgeGrader(judge=judge, rubric=["Quality"]), max_attempts=1)

    result = loop.run("Draft", trigger=Event(kind="test", payload={"text": "Draft"}))

    assert result.passed is True
    assert result.trace.verification_results[0].feedback == "looks good"
    assert judge.calls[0]["trace"]["trigger"]["kind"] == "test"
