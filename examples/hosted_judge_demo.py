from __future__ import annotations

from loop_engineering_agent import OpenAIJudge


# This example is intentionally not executed in CI because it requires an API key.
# Set OPENAI_API_KEY, then run:
#   python examples/hosted_judge_demo.py


def main() -> None:
    judge = OpenAIJudge(model="gpt-4o-mini")
    print(
        judge(
            {
                "instructions": "Return JSON only.",
                "rubric": ["Mention verification loop"],
                "task": "Draft a reliable agent plan",
                "output": "A plan with a verification loop.",
                "trace": {"steps": []},
            }
        )
    )


if __name__ == "__main__":
    main()
