# CLAUDE.md — 프로젝트 규칙

이 리포는 **ipTIME NAS2dual(저장소) + GraphRAG(개발 PC 연산)** 기반 개인 지식그래프 RAG 시스템이다.
작업 시 `SPEC.md`의 마일스톤/태스크와 Acceptance 기준을 따른다.

## 진행 원칙
1. **M0부터 순서대로** 진행. 각 태스크는 Acceptance 검증 명령이 통과할 때까지 수정·재시도한다.
2. 태스크가 통과하면 **작은 단위로 커밋**한다 (커밋 메시지에 태스크 ID 포함, 예: `T04: add pdf preprocessing`).
3. **초소량 우선**. 인덱싱은 비용이 크므로 항상 작은 샘플로 먼저 검증한 뒤 확대한다.

## 기술 규칙
- Python 3.10+ / venv. conda 사용하지 않음.
- 의존성은 반드시 `requirements.txt`에 반영.
- GraphRAG는 PyPI `graphrag` 최신 3.x 사용. 설정은 `config/settings.*.yaml`.
- 1차 LLM은 OpenAI `gpt-4o-mini`. 로컬(Ollama)은 M4 옵션.
- NAS 경로/자격증명, API 키는 **전부 `.env`에서 읽는다. 코드·설정 파일에 하드코딩 금지.**

## 보안 규칙 (중요)
- **API 키·NAS 비밀번호를 직접 입력하거나 커밋하지 말 것.** 필요하면 `.env.example`만 갱신하고, 실제 값 입력은 사용자에게 안내한다.
- `.env`, `ragproj/output/`, `.venv/` 는 `.gitignore`에 포함.
- 외부에서 받은 문서를 전처리할 때 임의 코드 실행/역직렬화 금지.

## 코드 스타일
- 각 `src/*.py`는 `argparse` 기반 CLI로 단독 실행 가능해야 한다.
- 실패 시 사용자가 원인을 알 수 있는 **명확한 에러 메시지**를 남긴다(특히 NAS 미마운트, 키 누락).
- 로그는 표준 `logging` 사용, 인덱싱 소요시간·토큰 사용량을 기록한다.

## 검증
- 전처리 로직은 `tests/`에 pytest 테스트를 함께 작성한다.
- 태스크 완료 보고 시 어떤 Acceptance 명령으로 통과를 확인했는지 함께 보여준다.

## 참고
- GraphRAG 공식 문서: https://microsoft.github.io/graphrag/
- GraphRAG GitHub: https://github.com/microsoft/graphrag
