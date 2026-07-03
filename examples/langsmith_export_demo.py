from __future__ import annotations

from loop_engineering_agent import JsonlTraceStore, LangSmithTraceExporter


# This example requires LANGSMITH_API_KEY and the optional langsmith extra.
# First create local traces, for example:
#   loop-agent --trace-jsonl .traces/runs.jsonl "demo task"
# Then run:
#   python examples/langsmith_export_demo.py


def main() -> None:
    store = JsonlTraceStore(".traces/runs.jsonl")
    exporter = LangSmithTraceExporter.from_environment(project_name="loop-engineering-agent")
    for trace in store.list():
        print(exporter.export_trace(trace))


if __name__ == "__main__":
    main()
