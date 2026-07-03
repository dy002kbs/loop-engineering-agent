from __future__ import annotations

from pprint import pprint

from loop_engineering_agent import AgentConfig, AgentLoop, LangChainAgentModel, Tool


class FakeLangChainRunnable:
    def invoke(self, payload):
        task = payload["messages"][-1]["content"]
        return {"messages": [{"role": "assistant", "content": f"LangChain-style final answer for: {task}"}]}


def fake_create_agent(**kwargs):
    print("create_agent called with:", sorted(kwargs))
    return FakeLangChainRunnable()


def main() -> None:
    adapter = LangChainAgentModel.from_create_agent(
        create_agent=fake_create_agent,
        model="fake-model",
        tools=[Tool("noop", lambda: "ok", description="No-op tool")],
        system_prompt="You are a LangChain-backed loop engineer.",
    )
    agent = AgentLoop(model=adapter, tools=[], config=AgentConfig(system_prompt="Outer harness prompt."))
    pprint(agent.run("Draft a loop-engineered agent plan").output)


if __name__ == "__main__":
    main()
