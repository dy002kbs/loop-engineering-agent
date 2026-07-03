# Loop engineering 확장 구현 노트

이 문서는 기존 reference harness에 추가한 확장의 의도와 사용법을 정리합니다.

## 1. Trace persistence

### 구현

- `trace_to_dict(trace)`
- `trace_from_dict(data)`
- `JsonlTraceStore(path)`
- `SQLiteTraceStore(path)`

### 이유

Hill-climbing loop는 단일 실행의 메모리 trace만으로는 약합니다. 여러 run의 실패 패턴을 누적해야 prompt/rubric/tool 개선 신호가 생깁니다. 그래서 trace를 JSONL 또는 SQLite로 저장할 수 있게 했습니다.

### 사용

```python
from loop_engineering_agent import JsonlTraceStore

store = JsonlTraceStore(".traces/runs.jsonl")
store.append(result.trace)
traces = list(store.list())
```

CLI:

```bash
loop-agent --trace-jsonl .traces/runs.jsonl "task"
loop-agent --analyze-jsonl .traces/runs.jsonl
```

## 2. LLM-as-a-judge grader

### 구현

- `LLMJudgeGrader`

### 설계

특정 provider SDK에 묶지 않고 `judge(payload)` 형태의 callable/object를 주입하게 했습니다. 이러면 테스트에서는 fake judge를 쓰고, 실제 운영에서는 OpenAI/Anthropic/LangChain judge를 wrapper로 붙일 수 있습니다.

Judge는 아래 형태를 반환하면 됩니다.

```json
{
  "passed": true,
  "feedback": "looks good",
  "details": {"score": 0.9}
}
```

## 2-1. Hosted judge wrappers

### 구현

- `OpenAIJudge`
- `AnthropicJudge`
- `judge_messages(payload)`
- `parse_judge_response(raw)`

### 설계

`LLMJudgeGrader`의 provider-neutral 계약은 유지하고, OpenAI/Anthropic SDK 호출만 얇은 wrapper로 분리했습니다.

- 기본 설치에는 hosted SDK가 포함되지 않습니다.
- `python -m pip install -e .[llm]`로 OpenAI/Anthropic SDK를 선택 설치합니다.
- 테스트는 fake client를 주입하므로 API key 없이 실행됩니다.
- OpenAI는 Responses API를 우선 사용하고, fake/legacy client를 위해 Chat Completions fallback도 지원합니다.
- Anthropic은 Messages API를 사용합니다.

### 사용

```python
from loop_engineering_agent import LLMJudgeGrader, OpenAIJudge

grader = LLMJudgeGrader(
    judge=OpenAIJudge(model="gpt-4o-mini"),
    rubric=["Mention verification loop", "Be concrete"],
)
```

```python
from loop_engineering_agent import AnthropicJudge, LLMJudgeGrader

grader = LLMJudgeGrader(
    judge=AnthropicJudge(model="claude-3-5-sonnet-latest"),
    rubric=["Mention verification loop", "Be concrete"],
)
```

## 3. LangChain create_agent adapter

### 구현

- `LangChainAgentModel`

### 설계

LangChain `create_agent`가 반환한 runnable을 `AgentLoop`의 `Model` protocol에 맞게 감싸는 adapter입니다. LangChain은 optional extra로 두었습니다.

```python
adapter = LangChainAgentModel.from_create_agent(
    model="anthropic:claude-sonnet-4",
    tools=[...],
    system_prompt="You are a loop engineer.",
)
agent = AgentLoop(model=adapter, tools=[], config=config)
```

## 4. FastAPI webhook/cron server

### 구현

- `CronJob`
- `create_app(event_loop=..., trace_store=..., cron_jobs=...)`
- `GET /health`
- `POST /webhooks/{event_kind}`
- `POST /cron/{job_name}/run`

### 사용

```bash
python -m pip install -e .[server]
PYTHONPATH=src uvicorn examples.server_app:app --reload
```

Webhook:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/slack.message \
  -H 'Content-Type: application/json' \
  -d '{"text":"Improve docs"}'
```

Cron-style trigger:

```bash
curl -X POST http://127.0.0.1:8000/cron/nightly-docs/run
```

## 5. LangSmith export/import

### 구현

- `langsmith_run_payloads(trace, project_name=...)`
- `LangSmithTraceExporter`
- `LangSmithTraceImporter`
- `write_langsmith_payloads_jsonl(path, traces, project_name=...)`
- CLI options:
  - `--export-langsmith-jsonl`
  - `--export-langsmith-sqlite`
  - `--import-langsmith-jsonl`
  - `--import-langsmith-sqlite`
  - `--langsmith-dry-run-jsonl`

### 설계

Local trace를 LangSmith root run + child run payload로 변환합니다.

- root run: 전체 agent/verification 실행
- tool child run: 각 tool call/observation
- verification child run: 각 grader 결과
- root run `extra.loop_engineering_trace`에 원본 trace를 넣어 import/round-trip 가능하게 유지

LangSmith SDK도 optional입니다. 실제 API 호출은 `python -m pip install -e .[langsmith]`가 필요하지만, payload dry-run은 기본 설치만으로 가능합니다.

### Dry-run export

```bash
loop-agent --export-langsmith-jsonl .traces/runs.jsonl \
  --langsmith-project loop-engineering-agent \
  --langsmith-dry-run-jsonl .traces/langsmith-payloads.jsonl
```

### 실제 export

```bash
python -m pip install -e .[langsmith]
export LANGSMITH_API_KEY=...
loop-agent --export-langsmith-jsonl .traces/runs.jsonl \
  --langsmith-project loop-engineering-agent
```

### Import

```bash
loop-agent --import-langsmith-jsonl .traces/imported.jsonl \
  --langsmith-project loop-engineering-agent \
  --langsmith-limit 50
```

## 운영상 다음 고려사항

- Webhook signature 검증
- API token 또는 Basic auth
- Cron endpoint의 idempotency key
- Trace에 포함될 수 있는 민감 정보 masking
- LangSmith feedback/evaluation API에 grader 결과 기록
- OpenTelemetry export
- GitHub issue/PR 생성은 사람 승인 gate 뒤에서만 실행
