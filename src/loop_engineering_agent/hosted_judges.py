from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


DEFAULT_JUDGE_INSTRUCTIONS = (
    "You are an LLM-as-a-judge evaluator. Grade the candidate output against "
    "the rubric and return JSON only with keys: passed:boolean, feedback:string, "
    "details:object. Do not include markdown fences."
)


def _payload_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "rubric": payload.get("rubric", []),
            "task": payload.get("task", ""),
            "candidate_output": payload.get("output", ""),
            "trace": payload.get("trace", {}),
        },
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )


def judge_messages(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Build provider-neutral judge messages from an LLMJudgeGrader payload."""

    instructions = str(payload.get("instructions") or DEFAULT_JUDGE_INSTRUCTIONS)
    if "JSON" not in instructions.upper():
        instructions = instructions.rstrip() + " Return JSON only."
    return instructions, _payload_text(payload)


def parse_judge_response(raw: Mapping[str, Any] | str) -> dict[str, Any]:
    """Parse a provider response into the judge result contract."""

    if isinstance(raw, Mapping):
        return dict(raw)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        lowered = text.lower()
        return {
            "passed": "pass" in lowered or "true" in lowered or "looks good" in lowered,
            "feedback": raw,
            "details": {},
        }
    if not isinstance(parsed, Mapping):
        return {"passed": False, "feedback": f"Invalid judge JSON: {parsed!r}", "details": {}}
    return dict(parsed)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


class OpenAIJudge:
    """OpenAI-backed judge callable for LLMJudgeGrader.

    The wrapper defaults to the Responses API when available, falls back to
    Chat Completions for older/fake clients, and stays optional by accepting an
    injected client in tests or importing `openai.OpenAI` only when needed.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        client: Any | None = None,
        temperature: float | None = 0,
        request_kwargs: Mapping[str, Any] | None = None,
    ):
        self.model = model
        self.client = client
        self.temperature = temperature
        self.request_kwargs = dict(request_kwargs or {})

    def __call__(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        client = self.client or self._default_client()
        system, user = judge_messages(payload)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        if hasattr(client, "responses"):
            raw_response = client.responses.create(
                model=self.model,
                input=messages,
                temperature=self.temperature,
                **self.request_kwargs,
            )
            return parse_judge_response(self._extract_responses_text(raw_response))

        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            raw_response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                **self.request_kwargs,
            )
            return parse_judge_response(self._extract_chat_text(raw_response))

        raise TypeError("OpenAIJudge client must expose .responses.create or .chat.completions.create")

    def _default_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError("Install the llm extra to use OpenAIJudge: python -m pip install -e .[llm]") from exc
        return OpenAI()

    def _extract_responses_text(self, response: Any) -> str:
        output_text = _get(response, "output_text")
        if output_text:
            return str(output_text)
        output = _get(response, "output", default=[])
        chunks: list[str] = []
        for item in output or []:
            content = _get(item, "content", default=[])
            for block in content or []:
                text = _get(block, "text", default=_get(block, "content", default=None))
                if text:
                    chunks.append(str(text))
        if chunks:
            return "\n".join(chunks)
        return str(response)

    def _extract_chat_text(self, response: Any) -> str:
        choices = _get(response, "choices", default=[])
        if choices:
            message = _get(choices[0], "message", default={})
            content = _get(message, "content", default="")
            return str(content)
        return str(response)


class AnthropicJudge:
    """Anthropic-backed judge callable for LLMJudgeGrader."""

    def __init__(
        self,
        *,
        model: str = "claude-3-5-sonnet-latest",
        client: Any | None = None,
        max_tokens: int = 1024,
        temperature: float | None = 0,
        request_kwargs: Mapping[str, Any] | None = None,
    ):
        self.model = model
        self.client = client
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_kwargs = dict(request_kwargs or {})

    def __call__(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        client = self.client or self._default_client()
        system, user = judge_messages(payload)
        raw_response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            **self.request_kwargs,
        )
        return parse_judge_response(self._extract_message_text(raw_response))

    def _default_client(self) -> Any:
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError("Install the llm extra to use AnthropicJudge: python -m pip install -e .[llm]") from exc
        return Anthropic()

    def _extract_message_text(self, response: Any) -> str:
        content = _get(response, "content", default=[])
        chunks: list[str] = []
        for block in content or []:
            text = _get(block, "text", default=None)
            if text:
                chunks.append(str(text))
            elif isinstance(block, str):
                chunks.append(block)
        if chunks:
            return "\n".join(chunks)
        return str(response)
