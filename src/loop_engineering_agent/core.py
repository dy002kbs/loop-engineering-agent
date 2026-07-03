from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Protocol


class Model(Protocol):
    """Minimal model protocol for the agent loop.

    The context dict intentionally mirrors the data a LangChain create_agent
    harness would have available: system prompt, user task, feedback from the
    verifier, and prior tool observations.
    """

    def respond(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return either {"tool": name, "args": {...}} or {"final": text}."""


@dataclass(frozen=True)
class Event:
    """External trigger that starts the application/event-driven loop."""

    kind: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class AgentConfig:
    """Harness configuration that the hill-climbing loop can improve."""

    system_prompt: str
    rubric: list[str] = field(default_factory=list)
    max_steps: int = 8
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    observation: Any
    approved: bool = True
    error: str | None = None


@dataclass(frozen=True)
class StepTrace:
    tool_name: str
    args: Mapping[str, Any]
    observation: Any
    approved: bool = True
    error: str | None = None


@dataclass
class Trace:
    """A single run trace: task, tool calls, grader feedback, and trigger."""

    task: str
    system_prompt: str
    steps: list[StepTrace] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
    final_output: str | None = None
    trigger: Event | None = None
    feedback_history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRun:
    output: str
    trace: Trace


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    feedback: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerifiedRun:
    output: str
    passed: bool
    attempts: int
    trace: Trace


@dataclass(frozen=True)
class HarnessSuggestion:
    target: str
    rationale: str
    patch: str


class ScriptedModel:
    """Deterministic model for tests, demos, and offline smoke runs."""

    def __init__(self, responses: Iterable[Mapping[str, Any]]):
        self._responses = list(responses)
        self.calls: list[Mapping[str, Any]] = []

    def respond(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(dict(context))
        if not self._responses:
            raise RuntimeError("ScriptedModel has no responses left")
        return self._responses.pop(0)


class HumanApprovalGate:
    """Human-in-the-loop approval primitive for sensitive tool calls."""

    def __init__(self, policy: Mapping[str, str] | None = None):
        self.policy = dict(policy or {})
        self._approvals: set[str] = set()

    def requires_approval(self, tool_name: str) -> bool:
        return tool_name in self.policy and tool_name not in self._approvals

    def approve(self, tool_name: str) -> None:
        self._approvals.add(tool_name)

    def revoke(self, tool_name: str) -> None:
        self._approvals.discard(tool_name)


class Tool:
    """Tool wrapper used by the agent loop."""

    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        description: str = "",
        approval_gate: HumanApprovalGate | None = None,
    ):
        self.name = name
        self.func = func
        self.description = description
        self.approval_gate = approval_gate

    def invoke(self, args: Mapping[str, Any] | None = None) -> ToolResult:
        args = dict(args or {})
        if self.approval_gate and self.approval_gate.requires_approval(self.name):
            policy = self.approval_gate.policy.get(self.name, "sensitive")
            return ToolResult(
                tool_name=self.name,
                observation=f"Tool '{self.name}' requires human approval before {policy} action.",
                approved=False,
            )
        try:
            observation = self.func(**args)
        except Exception as exc:  # pragma: no cover - surfaced as trace data
            return ToolResult(tool_name=self.name, observation=str(exc), approved=True, error=type(exc).__name__)
        return ToolResult(tool_name=self.name, observation=observation, approved=True)


class AgentLoop:
    """Loop 1: model calls tools repeatedly until it emits a final output."""

    def __init__(self, *, model: Model, tools: Iterable[Tool], config: AgentConfig):
        self.model = model
        self.tools = {tool.name: tool for tool in tools}
        self.config = config

    def run(self, task: str, *, feedback: str | None = None, trigger: Event | None = None) -> AgentRun:
        trace = Trace(task=task, system_prompt=self.config.system_prompt, trigger=trigger)
        if feedback:
            trace.feedback_history.append(feedback)

        for _ in range(self.config.max_steps):
            response = self.model.respond(
                {
                    "system_prompt": self.config.system_prompt,
                    "task": task,
                    "feedback": feedback,
                    "tool_descriptions": {name: tool.description for name, tool in self.tools.items()},
                    "steps": [step.__dict__ for step in trace.steps],
                }
            )
            if "final" in response:
                output = str(response["final"])
                trace.final_output = output
                return AgentRun(output=output, trace=trace)

            tool_name = response.get("tool")
            if not isinstance(tool_name, str):
                raise ValueError(f"Model response must contain 'tool' or 'final': {response!r}")
            if tool_name not in self.tools:
                raise KeyError(f"Unknown tool requested by model: {tool_name}")

            args = response.get("args") or {}
            if not isinstance(args, Mapping):
                raise TypeError(f"Tool args must be a mapping, got {type(args).__name__}")
            result = self.tools[tool_name].invoke(args)
            trace.steps.append(
                StepTrace(
                    tool_name=result.tool_name,
                    args=dict(args),
                    observation=result.observation,
                    approved=result.approved,
                    error=result.error,
                )
            )

        raise RuntimeError(f"Agent exceeded max_steps={self.config.max_steps} without final output")


class DeterministicRubricGrader:
    """Loop 2 grader: deterministic rubric checks with actionable feedback."""

    def __init__(self, *, required_phrases: Iterable[str] = (), max_length: int | None = None):
        self.required_phrases = [phrase for phrase in required_phrases]
        self.max_length = max_length

    def grade(self, *, task: str, output: str, trace: Trace) -> VerificationResult:
        del task, trace
        failures: list[str] = []
        output_lower = output.lower()
        missing = [phrase for phrase in self.required_phrases if phrase.lower() not in output_lower]
        if missing:
            failures.append("Missing required phrases: " + ", ".join(missing))
        if self.max_length is not None and len(output) > self.max_length:
            failures.append(f"Output is {len(output)} chars; max allowed is {self.max_length}")

        if failures:
            return VerificationResult(passed=False, feedback="; ".join(failures), details={"missing": missing})
        return VerificationResult(passed=True, feedback="Rubric passed", details={"missing": []})


class VerificationLoop:
    """Loop 2: run the agent, grade it, and retry with feedback if needed."""

    def __init__(self, *, agent: AgentLoop, grader: DeterministicRubricGrader, max_attempts: int = 2):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.agent = agent
        self.grader = grader
        self.max_attempts = max_attempts

    def run(self, task: str, *, trigger: Event | None = None) -> VerifiedRun:
        feedback: str | None = None
        verification_results: list[VerificationResult] = []
        last_run: AgentRun | None = None

        for attempt in range(1, self.max_attempts + 1):
            last_run = self.agent.run(task, feedback=feedback, trigger=trigger)
            grade = self.grader.grade(task=task, output=last_run.output, trace=last_run.trace)
            verification_results.append(grade)
            last_run.trace.verification_results = list(verification_results)

            if grade.passed:
                return VerifiedRun(output=last_run.output, passed=True, attempts=attempt, trace=last_run.trace)
            feedback = grade.feedback

        assert last_run is not None
        return VerifiedRun(
            output=last_run.output,
            passed=False,
            attempts=self.max_attempts,
            trace=last_run.trace,
        )


class EventDrivenLoop:
    """Loop 3: turn external events into verified agent runs."""

    def __init__(self, *, verification_loop: VerificationLoop, task_key: str = "text"):
        self.verification_loop = verification_loop
        self.task_key = task_key
        self.traces: list[Trace] = []

    def handle(self, event: Event) -> VerifiedRun:
        task = self._task_from_event(event)
        result = self.verification_loop.run(task, trigger=event)
        result.trace.trigger = event
        self.traces.append(result.trace)
        return result

    def _task_from_event(self, event: Event) -> str:
        if self.task_key in event.payload:
            return str(event.payload[self.task_key])
        if "task" in event.payload:
            return str(event.payload["task"])
        return str(dict(event.payload))


class HillClimber:
    """Loop 4: analyze traces and propose harness improvements."""

    def __init__(self, *, min_failure_count: int = 2):
        self.min_failure_count = min_failure_count

    def analyze(self, traces: Iterable[Trace]) -> list[HarnessSuggestion]:
        feedback_counts: dict[str, int] = {}
        missing_phrases: dict[str, int] = {}
        for trace in traces:
            for result in trace.verification_results:
                if result.passed:
                    continue
                feedback_counts[result.feedback] = feedback_counts.get(result.feedback, 0) + 1
                for phrase in result.details.get("missing", []) if result.details else []:
                    key = str(phrase)
                    missing_phrases[key] = missing_phrases.get(key, 0) + 1

        suggestions: list[HarnessSuggestion] = []
        for phrase, count in missing_phrases.items():
            if count >= self.min_failure_count:
                suggestions.append(
                    HarnessSuggestion(
                        target="system_prompt",
                        rationale=f"{count} failed trace(s) missed required concept: {phrase}",
                        patch=f"Always address '{phrase}' when relevant, and make the criterion explicit.",
                    )
                )
                suggestions.append(
                    HarnessSuggestion(
                        target="rubric",
                        rationale=f"Promote recurring missing concept to rubric: {phrase}",
                        patch=f"Must mention {phrase}.",
                    )
                )

        if not suggestions:
            for feedback, count in feedback_counts.items():
                if count >= self.min_failure_count:
                    suggestions.append(
                        HarnessSuggestion(
                            target="system_prompt",
                            rationale=f"{count} failed trace(s) shared verifier feedback",
                            patch=f"Avoid verifier failure: {feedback}",
                        )
                    )
        return suggestions

    def apply(self, config: AgentConfig, suggestions: Iterable[HarnessSuggestion]) -> AgentConfig:
        system_prompt = config.system_prompt
        rubric = list(config.rubric)
        metadata = dict(config.metadata)
        applied: list[dict[str, str]] = []

        for suggestion in suggestions:
            applied.append(
                {"target": suggestion.target, "rationale": suggestion.rationale, "patch": suggestion.patch}
            )
            if suggestion.target == "system_prompt" and suggestion.patch not in system_prompt:
                system_prompt = system_prompt.rstrip() + "\n\nHill-climb update: " + suggestion.patch
            elif suggestion.target == "rubric" and suggestion.patch not in rubric:
                rubric.append(suggestion.patch)

        metadata["hill_climb_suggestions"] = applied
        return replace(config, system_prompt=system_prompt, rubric=rubric, metadata=metadata)
