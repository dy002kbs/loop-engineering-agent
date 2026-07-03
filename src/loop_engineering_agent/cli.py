from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .core import (
    AgentConfig,
    AgentLoop,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    HillClimber,
    ScriptedModel,
    VerificationLoop,
)


def build_demo_loop() -> EventDrivenLoop:
    """Build an offline demo that exercises all four loops without an API key."""

    model = ScriptedModel(
        [
            {"final": "Draft a basic agent."},
            {
                "final": (
                    "Draft an agent with an agent loop, verification loop, "
                    "event-driven loop, hill-climbing loop, and human oversight."
                )
            },
        ]
    )
    config = AgentConfig(
        system_prompt="You convert work requests into reliable loop-engineered agent plans.",
        rubric=["Mention verification loop", "Mention event-driven loop", "Mention hill-climbing loop"],
    )
    agent = AgentLoop(model=model, tools=[], config=config)
    verified = VerificationLoop(
        agent=agent,
        grader=DeterministicRubricGrader(
            required_phrases=["verification loop", "event-driven loop", "hill-climbing loop"]
        ),
        max_attempts=2,
    )
    return EventDrivenLoop(verification_loop=verified)


def run_demo(task: str) -> dict:
    app_loop = build_demo_loop()
    result = app_loop.handle(Event(kind="cli.demo", payload={"text": task}))
    suggestions = HillClimber(min_failure_count=1).analyze(app_loop.traces)
    return {
        "passed": result.passed,
        "attempts": result.attempts,
        "output": result.output,
        "trigger": asdict(result.trace.trigger) if result.trace.trigger else None,
        "verification_feedback": [asdict(item) for item in result.trace.verification_results],
        "hill_climb_suggestions": [asdict(item) for item in suggestions],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Loop Engineering Agent offline demo.")
    parser.add_argument("task", nargs="?", default="Turn loop engineering into an agent harness")
    args = parser.parse_args(argv)
    print(json.dumps(run_demo(args.task), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
