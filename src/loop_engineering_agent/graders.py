from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Mapping, Protocol

from .core import Trace, VerificationResult
from .persistence import trace_to_dict


class JudgeCallable(Protocol):
    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | str: ...


class LLMJudgeGrader:
    """LLM-as-a-judge grader with deterministic, injectable judge backend.

    The backend can be a callable, an object with `.judge(payload)`, or an
    object with `.respond(payload)`. This keeps the core package independent of
    any hosted LLM provider while preserving the same verification-loop shape.
    """

    def __init__(
        self,
        *,
        judge: JudgeCallable | Any,
        rubric: list[str] | tuple[str, ...],
        instructions: str | None = None,
    ):
        self.judge = judge
        self.rubric = list(rubric)
        self.instructions = instructions or (
            "Grade the agent output against the rubric. Return JSON with "
            "passed:boolean, feedback:string, and details:object."
        )

    def grade(self, *, task: str, output: str, trace: Trace) -> VerificationResult:
        payload = {
            "instructions": self.instructions,
            "rubric": list(self.rubric),
            "task": task,
            "output": output,
            "trace": trace_to_dict(trace),
        }
        raw = self._call_judge(payload)
        parsed = self._parse_response(raw)
        return VerificationResult(
            passed=bool(parsed.get("passed", False)),
            feedback=str(parsed.get("feedback") or "LLM judge returned no feedback."),
            details=dict(parsed.get("details") or {}),
        )

    def _call_judge(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | str:
        if callable(self.judge):
            return self.judge(payload)
        if hasattr(self.judge, "judge"):
            return self.judge.judge(payload)
        if hasattr(self.judge, "respond"):
            return self.judge.respond(payload)
        raise TypeError("judge must be callable or expose .judge(payload)/.respond(payload)")

    def _parse_response(self, raw: Mapping[str, Any] | str) -> dict[str, Any]:
        if isinstance(raw, Mapping):
            return dict(raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            lowered = raw.lower()
            return {
                "passed": "pass" in lowered or "true" in lowered or "looks good" in lowered,
                "feedback": raw,
                "details": {},
            }
        if not isinstance(data, Mapping):
            return {"passed": False, "feedback": f"Invalid judge JSON: {data!r}", "details": {}}
        return dict(data)
