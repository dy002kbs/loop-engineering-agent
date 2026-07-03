# 1번~4번 확장 구현 노트

이 문서는 기존 reference harness에 추가한 4가지 확장의 의도와 사용법을 정리합니다.

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

## 운영상 다음 고려사항

- Webhook signature 검증
- API token 또는 Basic auth
- Cron endpoint의 idempotency key
- Trace에 포함될 수 있는 민감 정보 masking
- LangSmith/OpenTelemetry export
- GitHub issue/PR 생성은 사람 승인 gate 뒤에서만 실행
