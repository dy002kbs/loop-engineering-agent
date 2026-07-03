from __future__ import annotations

from loop_engineering_agent import AgentConfig, AgentLoop, LLMJudgeGrader, OpenAIJudge, AnthropicJudge, ScriptedModel


class _OpenAIResponse:
    output_text = '{"passed": true, "feedback": "openai ok", "details": {"score": 0.92}}'


class _FakeOpenAIResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _OpenAIResponse()


class _FakeOpenAIClient:
    def __init__(self):
        self.responses = _FakeOpenAIResponses()


class _AnthropicTextBlock:
    text = '{"passed": false, "feedback": "anthropic says add verification", "details": {"score": 0.41}}'


class _AnthropicResponse:
    content = [_AnthropicTextBlock()]


class _FakeAnthropicMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _AnthropicResponse()


class _FakeAnthropicClient:
    def __init__(self):
        self.messages = _FakeAnthropicMessages()


def _sample_payload():
    return {
        "instructions": "Return JSON only.",
        "rubric": ["Mention verification loop"],
        "task": "Draft a reliable agent plan",
        "output": "A draft with no verifier.",
        "trace": {"task": "Draft a reliable agent plan", "steps": []},
    }


def _sample_trace():
    return AgentLoop(
        model=ScriptedModel([{"final": "unused"}]),
        tools=[],
        config=AgentConfig(system_prompt="test"),
    ).run("seed").trace


def test_openai_judge_calls_responses_api_and_returns_structured_result() -> None:
    client = _FakeOpenAIClient()
    judge = OpenAIJudge(client=client, model="gpt-test", temperature=0)

    result = judge(_sample_payload())

    assert result == {"passed": True, "feedback": "openai ok", "details": {"score": 0.92}}
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["temperature"] == 0
    assert call["input"][0]["role"] == "system"
    assert "Return JSON only" in call["input"][0]["content"]
    assert call["input"][1]["role"] == "user"
    assert "Draft a reliable agent plan" in call["input"][1]["content"]


def test_anthropic_judge_calls_messages_api_and_returns_structured_result() -> None:
    client = _FakeAnthropicClient()
    judge = AnthropicJudge(client=client, model="claude-test", max_tokens=512, temperature=0)

    result = judge(_sample_payload())

    assert result["passed"] is False
    assert result["feedback"] == "anthropic says add verification"
    call = client.messages.calls[0]
    assert call["model"] == "claude-test"
    assert call["max_tokens"] == 512
    assert call["temperature"] == 0
    assert "Return JSON only" in call["system"]
    assert call["messages"][0]["role"] == "user"
    assert "Mention verification loop" in call["messages"][0]["content"]


def test_hosted_judge_wrapper_plugs_into_llm_judge_grader() -> None:
    client = _FakeOpenAIClient()
    grader = LLMJudgeGrader(judge=OpenAIJudge(client=client, model="gpt-test"), rubric=["Quality"])

    result = grader.grade(task="Draft", output="Draft with quality.", trace=_sample_trace())

    assert result.passed is True
    assert result.feedback == "openai ok"
    assert result.details["score"] == 0.92
