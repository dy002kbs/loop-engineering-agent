# Loop Engineering Agent

LangChain 블로그 [The Art of Loop Engineering](https://www.langchain.com/blog/the-art-of-loop-engineering)의 핵심 아이디어를 로컬에서 바로 실행 가능한 **에이전트 하니스(reference harness)** 로 구현한 프로젝트입니다.

> 목적: “좋은 모델 하나”가 아니라, 모델을 둘러싼 반복 루프를 설계해서 더 안정적으로 일하고, 검증하고, 이벤트로 실행하고, 실행 흔적(trace)으로 스스로 개선하는 에이전트 구조를 보여줍니다.

## 구현한 4+1 루프

| 블로그 개념 | 이 프로젝트의 구현 | 역할 |
| --- | --- | --- |
| Loop 1. Agent loop | `AgentLoop` | 모델이 도구를 호출하다가 최종 답을 낼 때까지 반복합니다. |
| Loop 2. Verification loop | `VerificationLoop`, `DeterministicRubricGrader` | 결과를 루브릭으로 채점하고, 실패하면 피드백을 다음 시도에 넣어 재시도합니다. |
| Loop 3. Event-driven loop | `EventDrivenLoop`, `Event` | Slack 메시지, 웹훅, 크론 같은 외부 이벤트를 에이전트 실행으로 변환합니다. |
| Loop 4. Hill-climbing loop | `HillClimber` | 실행 trace와 grader 피드백을 분석해 prompt/rubric 개선안을 제안하고 적용합니다. |
| Human oversight | `HumanApprovalGate` | 민감한 도구 호출은 사람 승인 전까지 막습니다. |

## 왜 LangChain API를 직접 강제하지 않았나?

블로그는 LangChain/LangSmith의 `create_agent`, `RubricMiddleware`, Deployment triggers, Engine을 설명합니다. 이 저장소는 그 패턴을 **API 키 없이도 테스트 가능한 순수 Python reference implementation** 으로 먼저 구현했습니다.

- 로컬/CI에서 deterministic test 가능
- 외부 LLM 비용 없이 구조 학습 가능
- 이후 `ScriptedModel` 대신 LangChain `create_agent`나 실제 LLM wrapper를 끼우기 쉬운 구조

## 빠른 실행

```bash
cd C:/Users/bbski/dev/loop-engineering-agent
python -m pytest -q
PYTHONPATH=src python -m loop_engineering_agent.cli "문서 개선 요청을 loop engineering agent로 처리해줘"
```

또는 설치 후 CLI:

```bash
python -m pip install -e .
loop-agent "Turn loop engineering into an agent harness"
```

## Python 사용 예시

```python
from loop_engineering_agent import (
    AgentConfig,
    AgentLoop,
    DeterministicRubricGrader,
    Event,
    EventDrivenLoop,
    ScriptedModel,
    VerificationLoop,
)

model = ScriptedModel([
    {"final": "Draft a basic agent."},
    {"final": "Draft an agent with verification loop, event-driven loop, and hill-climbing loop."},
])

agent = AgentLoop(
    model=model,
    tools=[],
    config=AgentConfig(system_prompt="You design reliable agents."),
)
verified = VerificationLoop(
    agent=agent,
    grader=DeterministicRubricGrader(
        required_phrases=["verification loop", "event-driven loop", "hill-climbing loop"]
    ),
    max_attempts=2,
)
app = EventDrivenLoop(verification_loop=verified)

result = app.handle(Event(kind="slack.message", payload={"text": "Improve docs"}))
print(result.output)
```

## 프로젝트 구조

```text
src/loop_engineering_agent/
  __init__.py
  core.py      # loop stack implementation
  cli.py       # offline demo CLI
tests/
  test_loop_stack.py
docs/
  article-notes-ko.md
examples/
  docs_agent_demo.py
.github/workflows/
  ci.yml
```

## 테스트가 보장하는 것

- Agent loop가 tool call → observation → final output 순서로 trace를 남기는지
- Verification loop가 rubric 실패 피드백을 다음 시도에 넣고 재시도하는지
- Event-driven loop가 외부 이벤트 payload를 task로 변환해 실행하는지
- Hill-climbing loop가 반복 실패 trace에서 prompt/rubric 개선안을 만드는지
- Human approval gate가 민감 tool을 승인 전까지 차단하는지

## 다음 확장 아이디어

1. `ScriptedModel`을 LangChain `create_agent` 기반 wrapper로 교체
2. `DeterministicRubricGrader` 옆에 LLM-as-a-judge grader 추가
3. FastAPI webhook endpoint로 GitHub/Slack/Telegram 이벤트 연결
4. trace를 JSONL/SQLite/LangSmith로 저장
5. `HillClimber`가 GitHub issue/PR까지 자동 생성하도록 확장

## 출처

- Sydney Runkle, “The Art of Loop Engineering”, LangChain Blog, 2026-06-16.
- 이 저장소는 원문을 그대로 복제하지 않고, 핵심 설계 패턴을 학습/실행 가능한 코드로 재해석한 예제입니다.
