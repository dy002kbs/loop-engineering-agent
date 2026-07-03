"""Loop Engineering Agent reference package.

This package turns the loop-engineering stack described in LangChain's
"The Art of Loop Engineering" into a small, testable agent harness:
agent loop, verification loop, event-driven loop, hill-climbing loop, and
human approval gates for sensitive actions.
"""

from .adapters import LangChainAgentModel
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
from .graders import LLMJudgeGrader
from .hosted_judges import AnthropicJudge, OpenAIJudge, judge_messages, parse_judge_response
from .langsmith import (
    LangSmithExportResult,
    LangSmithTraceExporter,
    LangSmithTraceImporter,
    langsmith_run_payloads,
    write_langsmith_payloads_jsonl,
)
from .persistence import JsonlTraceStore, SQLiteTraceStore, trace_from_dict, trace_to_dict
from .server import CronJob, create_app, verified_run_to_dict

__all__ = [
    "AgentConfig",
    "AgentLoop",
    "AgentRun",
    "AnthropicJudge",
    "CronJob",
    "DeterministicRubricGrader",
    "Event",
    "EventDrivenLoop",
    "HarnessSuggestion",
    "HillClimber",
    "HumanApprovalGate",
    "JsonlTraceStore",
    "LangChainAgentModel",
    "LangSmithExportResult",
    "LangSmithTraceExporter",
    "LangSmithTraceImporter",
    "LLMJudgeGrader",
    "OpenAIJudge",
    "ScriptedModel",
    "SQLiteTraceStore",
    "StepTrace",
    "Tool",
    "ToolResult",
    "Trace",
    "VerificationLoop",
    "VerificationResult",
    "VerifiedRun",
    "create_app",
    "judge_messages",
    "langsmith_run_payloads",
    "parse_judge_response",
    "trace_from_dict",
    "trace_to_dict",
    "verified_run_to_dict",
    "write_langsmith_payloads_jsonl",
]
