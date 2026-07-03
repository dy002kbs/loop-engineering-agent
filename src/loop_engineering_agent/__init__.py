"""Loop Engineering Agent reference package.

This package turns the loop-engineering stack described in LangChain's
"The Art of Loop Engineering" into a small, testable agent harness:
agent loop, verification loop, event-driven loop, hill-climbing loop, and
human approval gates for sensitive actions.
"""

from .core import (
    AgentConfig,
    AgentLoop,
    AgentRun,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    HarnessSuggestion,
    HillClimber,
    HumanApprovalGate,
    ScriptedModel,
    StepTrace,
    Tool,
    ToolResult,
    Trace,
    VerificationLoop,
    VerificationResult,
    VerifiedRun,
)

__all__ = [
    "AgentConfig",
    "AgentLoop",
    "AgentRun",
    "DeterministicRubricGrader",
    "Event",
    "EventDrivenLoop",
    "HarnessSuggestion",
    "HillClimber",
    "HumanApprovalGate",
    "ScriptedModel",
    "StepTrace",
    "Tool",
    "ToolResult",
    "Trace",
    "VerificationLoop",
    "VerificationResult",
    "VerifiedRun",
]
