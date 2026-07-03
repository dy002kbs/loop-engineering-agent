from __future__ import annotations

from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    LangChainAgentModel,
    Tool,
)


class FakeRunnable:
    def __init__(self, response):
        self.response = response
        self.inputs = []

    def invoke(self, payload):
        self.inputs.append(payload)
        return self.response


def test_langchain_create_agent_adapter_builds_runnable_and_maps_final_message() -> None:
    captured = {}
    runnable = FakeRunnable({"messages": [{"role": "assistant", "content": "LangChain final plan."}]})

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return runnable

    adapter = LangChainAgentModel.from_create_agent(
        create_agent=fake_create_agent,
        model="fake-model",
        tools=[Tool("noop", lambda: "ok", description="No-op")],
        system_prompt="You are a loop engineer.",
    )
    agent = AgentLoop(model=adapter, tools=[], config=AgentConfig(system_prompt="outer prompt"))

    result = agent.run("Draft using LangChain")

    assert captured["model"] == "fake-model"
    assert captured["system_prompt"] == "You are a loop engineer."
    assert captured["tools"][0].name == "noop"
    assert runnable.inputs[0]["messages"][-1]["content"] == "Draft using LangChain"
    assert runnable.inputs[0]["context"]["system_prompt"] == "outer prompt"
    assert result.output == "LangChain final plan."


def test_langchain_adapter_passes_through_tool_request_shape() -> None:
    runnable = FakeRunnable({"tool": "read_doc", "args": {"path": "README.md"}})
    adapter = LangChainAgentModel(runnable)

    response = adapter.respond({"task": "read first", "steps": []})

    assert response == {"tool": "read_doc", "args": {"path": "README.md"}}
