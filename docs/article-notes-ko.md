# The Art of Loop Engineering — 한국어 구현 노트

원문: https://www.langchain.com/blog/the-art-of-loop-engineering

이 문서는 원문을 그대로 옮긴 번역본이 아니라, 구현을 위해 핵심 아이디어를 정리한 노트입니다.

## 한 줄 요약

에이전트의 경쟁력은 “한 번 호출하는 모델”보다, 모델을 둘러싼 반복 구조에 있다. 기본 agent loop 위에 검증 루프, 이벤트 루프, 개선 루프를 겹치면 에이전트가 더 안정적으로 일하고 운영 중 계속 나아진다.

## 1. Agent loop

- 핵심: LLM이 컨텍스트를 받고, 필요한 tool을 호출하고, 관찰 결과를 다시 받아 다음 행동을 정한다.
- 종료 조건: task가 끝났다고 판단하면 final output을 낸다.
- 구현 포인트:
  - tool registry
  - max step 제한
  - tool call / observation trace
  - 알 수 없는 tool, 잘못된 args, step 초과 처리

이 프로젝트에서는 `AgentLoop`, `Tool`, `Trace`, `StepTrace`로 구현했다.

## 2. Verification loop

- 기본 agent loop는 첫 결과가 항상 정확하지 않다.
- 따라서 agent 실행 후 grader가 결과를 rubric으로 평가한다.
- 실패하면 feedback을 agent에게 다시 넣어 재시도한다.
- trade-off: 비용과 지연 시간은 늘어나지만, production 수준에서는 품질 안정성이 더 중요하다.

이 프로젝트에서는 `VerificationLoop`와 `DeterministicRubricGrader`로 구현했다.

## 3. Event-driven loop

- 에이전트를 사람이 수동으로 호출하는 도구가 아니라, 시스템 안에서 계속 동작하는 컴포넌트로 만든다.
- 예: 새 문서 도착, Slack 메시지, cron schedule, webhook, GitHub event.
- 핵심은 event payload를 agent task로 안전하게 변환하고, trace에 trigger를 남기는 것이다.

이 프로젝트에서는 `Event`, `EventDrivenLoop`로 구현했다.

## 4. Hill-climbing loop

- 이전 세 루프가 “일을 자동화”한다면, 네 번째 루프는 “개선을 자동화”한다.
- 모든 agent run은 trace를 만든다.
- trace에는 tool call, grader feedback, 실패 패턴이 남는다.
- 분석 agent 또는 deterministic analyzer가 이 trace를 보고 prompt/tool/rubric/harness 설정 개선안을 만든다.
- 핵심은 바깥 루프의 결과가 단순히 다음 실행으로 돌아가는 것이 아니라, 안쪽 agent harness 자체를 업데이트한다는 점이다.

이 프로젝트에서는 `HillClimber`, `HarnessSuggestion`, `AgentConfig` 업데이트로 구현했다.

## 5. Human oversight

- 자동화는 사람을 제거한다는 뜻이 아니다.
- 링크 검사 같은 일은 자동 grader가 잘하지만, 대상 독자에 맞는 framing/taste 판단은 사람이 더 잘할 수 있다.
- 특히 금융, DB 변경, git push, 배포, 삭제 같은 민감 작업은 실행 전 human approval이 필요하다.

이 프로젝트에서는 `HumanApprovalGate`로 구현했다.

## 원문 → 코드 매핑

- `create_agent` 패턴 → `AgentLoop`
- `Tools` → `Tool`
- `RubricMiddleware` / `after_agent` hook → `VerificationLoop`
- cron/webhook/channel triggers → `EventDrivenLoop`
- LangSmith trace / Engine → `Trace` + `HillClimber`
- Human-in-the-loop primitive → `HumanApprovalGate`

## 구현 시 의도한 사용성

- API 키 없이도 테스트 가능해야 한다.
- trace가 사람이 읽을 수 있는 구조여야 한다.
- 검증 실패 feedback이 다음 attempt에 실제로 들어가야 한다.
- hill climbing은 최소한 prompt/rubric 개선안으로 연결되어야 한다.
- 민감 tool은 기본적으로 막고, 사람이 승인해야 실행되어야 한다.
