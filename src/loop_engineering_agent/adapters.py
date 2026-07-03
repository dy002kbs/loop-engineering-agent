from __future__ import annotations

from typing import Any, Iterable, Mapping

from .core import Tool


class LangChainAgentModel:
    """Adapter that lets a LangChain create_agent runnable drive AgentLoop.

    LangChain stays optional: tests can inject a fake `create_agent`, while real
    users can install the `langchain` extra and omit the argument.
    """

    def __init__(self, runnable: Any):
        self.runnable = runnable

    @classmethod
    def from_create_agent(
        cls,
        *,
        model: Any,
        tools: Iterable[Tool] | Iterable[Any],
        system_prompt: str,
        create_agent: Any | None = None,
        **kwargs: Any,
    ) -> "LangChainAgentModel":
        if create_agent is None:
            try:
                from langchain.agents import create_agent as create_agent  # type: ignore[no-redef]
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise ImportError(
                    "Install the langchain extra to use LangChainAgentModel.from_create_agent: "
                    "python -m pip install -e .[langchain]"
                ) from exc
        runnable = create_agent(model=model, tools=list(tools), system_prompt=system_prompt, **kwargs)
        return cls(runnable)

    def respond(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = {
            "messages": self._messages_from_context(context),
            "context": dict(context),
        }
        result = self.runnable.invoke(payload)
        return self._parse_result(result)

    def _messages_from_context(self, context: Mapping[str, Any]) -> list[dict[str, str]]:
        task = str(context.get("task", ""))
        feedback = context.get("feedback")
        if feedback:
            task = f"{task}\n\nVerifier feedback to address:\n{feedback}"
        return [{"role": "user", "content": task}]

    def _parse_result(self, result: Any) -> Mapping[str, Any]:
        if isinstance(result, Mapping):
            if "tool" in result or "final" in result:
                return dict(result)
            if "output" in result:
                return {"final": str(result["output"])}
            if "messages" in result:
                return self._parse_messages(result["messages"])
        if isinstance(result, str):
            return {"final": result}
        if hasattr(result, "content"):
            return {"final": str(result.content)}
        return {"final": str(result)}

    def _parse_messages(self, messages: Any) -> Mapping[str, Any]:
        if not messages:
            return {"final": ""}
        last = messages[-1]
        tool_calls = self._get(last, "tool_calls", default=None)
        if tool_calls:
            call = tool_calls[0]
            name = self._get(call, "name", default=self._get(call, "tool", default=""))
            args = self._get(call, "args", default={})
            return {"tool": str(name), "args": dict(args or {})}
        content = self._get(last, "content", default=last)
        return {"final": str(content)}

    def _get(self, value: Any, key: str, *, default: Any = None) -> Any:
        if isinstance(value, Mapping):
            return value.get(key, default)
        return getattr(value, key, default)
