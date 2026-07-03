from __future__ import annotations

from pprint import pprint

from loop_engineering_agent import AgentConfig, AgentLoop, Event, LLMJudgeGrader, ScriptedModel, VerificationLoop


def fake_judge(payload):
    output = payload["output"].lower()
    passed = "verification loop" in output and "event-driven loop" in output
    return {
        "passed": passed,
        "feedback": "ok" if passed else "Mention both verification loop and event-driven loop.",
        "details": {"score": 1.0 if passed else 0.4},
    }


def main() -> None:
    agent = AgentLoop(
        model=ScriptedModel([{"final": "A plan with verification loop and event-driven loop."}]),
        tools=[],
        config=AgentConfig(system_prompt="Draft reliable agent plans."),
    )
    loop = VerificationLoop(
        agent=agent,
        grader=LLMJudgeGrader(judge=fake_judge, rubric=["Quality", "Completeness"]),
        max_attempts=1,
    )
    result = loop.run("Draft a reliable agent", trigger=Event(kind="demo", payload={"text": "Draft"}))
    pprint({"passed": result.passed, "feedback": result.trace.verification_results[0].feedback})


if __name__ == "__main__":
    main()
