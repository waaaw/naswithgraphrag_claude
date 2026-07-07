# SPEC.md — NAS2dual + GraphRAG 개인 지식그래프 RAG 시스템

> Claude Code 실행용 개발 사양서. 각 태스크의 **Acceptance(검증 명령)** 가 통과할 때까지 구현·수정·재시도한 뒤 다음 태스크로 진행한다.

## 아키텍처 (확정)
NAS2dual은 ARM 듀얼코어 / RAM 2GB / Docker 미지원 → **저장소 전용**. 모든 연산은 개발 PC에서 수행하는 2-Tier 구조.

```
NAS2dual (//nas/graphrag/input, /artifacts)  ── SMB 마운트 ──  개발 PC (Python + GraphRAG + LLM)
데이터 흐름: NAS input/ → PC 동기화 → 전처리 → 인덱싱 → 결과 NAS 백업 → 질의는 PC 로컬 인덱스에서
```

## 기술 결정사항 (이 값을 따를 것)
| 항목 | 결정값 |
|---|---|
| Python | 3.10+ (권장 3.11), venv 사용 |
| 핵심 패키지 | `graphrag` (PyPI 최신 3.x) |
| 1차 LLM | OpenAI `gpt-4o-mini` + 임베딩 `text-embedding-3-small` |
| 2차 LLM(옵션) | Ollama `qwen2.5` + `nomic-embed-text` (비용 0, num_ctx 함정 주의) |
| 질의 UI | ① CLI 기본 ② Streamlit 선택 |
| 패키지 관리 | `requirements.txt` + venv |

⚠️ GraphRAG 인덱싱은 LLM 호출량이 많아 비용이 급증할 수 있음. **M0에서 초소량(수 KB) 문서로 먼저** 돌려 비용·시간 확인 후 실데이터로 확대.

## 리포지토리 구조
```
nas-graphrag/
├─ CLAUDE.md
├─ SPEC.md
├─ README.md            # T10에서 생성
├─ requirements.txt
├─ .env.example         # .env는 git 제외
├─ .gitignore
├─ config/
│   ├─ settings.openai.yaml
│   └─ settings.ollama.yaml   # 옵션
├─ src/
│   ├─ nas_sync.py       # T03
│   ├─ preprocess.py     # T04
│   ├─ index_runner.py   # T05
│   ├─ query_cli.py      # T06
│   └─ app.py            # T07 (옵션)
├─ ragproj/
│   ├─ input/
│   └─ output/
├─ scripts/
│   ├─ mount_nas.sh
│   └─ mount_nas.ps1
└─ tests/
    └─ test_preprocess.py
```

---

## M0 — 환경 & 스모크 테스트 (가장 먼저, 반드시 성공)

### T01 · 프로젝트 스캐폴딩
- **목표**: 위 리포 구조 생성, `requirements.txt`·`.gitignore`·`.env.example` 작성.
- **Acceptance**: `python -m venv .venv && pip install -r requirements.txt` 성공, `git status` 클린.

### T02 · GraphRAG 스모크 테스트 (초소량)
- **목표**: 공식 튜토리얼 데이터로 파이프라인이 끝까지 도는지 확인.
- **구현**:
  ```bash
  graphrag init --root ./ragproj
  # .env 에 GRAPHRAG_API_KEY=sk-... (사용자가 입력)
  # 5~10KB txt 하나만 input/ 에 넣는다
  graphrag index --root ./ragproj
  graphrag query --root ./ragproj --method global --query "핵심 주제는?"
  ```
- **Acceptance**: global 질의가 오류 없이 답변 반환. **인덱싱 소요시간·토큰 사용량을 로그로 남길 것.**

---

## M1 — NAS 연동 & 전처리

### T03 · NAS 동기화 (src/nas_sync.py)
- **목표**: NAS 원본 → PC 복사(`--pull`), 인덱싱 결과 → NAS 백업(`--push`).
- **구현**: OS 분기(Windows: `net use`/`robocopy`, Linux: `mount.cifs`/`rsync`). 마운트 경로·자격증명은 `.env`로 주입, **코드 하드코딩 금지**.
- **Acceptance**: `python src/nas_sync.py --pull` / `--push` 동작, 미마운트 시 명확한 에러.

### T04 · 문서 전처리 (src/preprocess.py)
- **목표**: pdf/docx/txt → 정제 UTF-8 txt → `ragproj/input/`.
- **구현**: pdf=`pypdf`/`pdfminer`, docx=`python-docx`, hwp는 미지원 경고. 공백·제어문자 정리, 파일당 1 txt.
- **Acceptance**: `pytest tests/test_preprocess.py` 통과, 샘플 pdf가 비어있지 않은 txt로 변환.

---

## M2 — 인덱싱 & CLI 질의

### T05 · 인덱싱 래퍼 (src/index_runner.py)
- **목표**: `graphrag index` 래핑(로그·소요시간·증분), 완료 후 T03 `--push` 자동 호출.
- **Acceptance**: `python src/index_runner.py` 1커맨드로 output 생성 + NAS 백업.

### T06 · CLI 질의 (src/query_cli.py)
- **목표**: global/local/drift 선택 질의.
  ```bash
  python src/query_cli.py --method global --q "이 문서들의 공통 주제는?"
  python src/query_cli.py --method local  --q "A프로젝트 담당자는 누구야?"
  ```
- **Acceptance**: 두 method 답변 반환, `--method` 기본 global, 잘못된 값은 친절한 에러.

---

## M3 — 질의 UI (선택) & 한국어 품질

### T07 · Streamlit UI (src/app.py)
- **목표**: 질문 입력 + method 선택 + 답변 표시. GUI는 단순·명확하게.
- **Acceptance**: `streamlit run src/app.py` 로 질의·응답 왕복 성공.

### T08 · 한국어 프롬프트 튜닝
- **목표**: 엔티티/관계 추출 품질 향상.
  ```bash
  graphrag prompt-tune --root ./ragproj --language Korean --domain "기술문서"
  ```
- **Acceptance**: 튜닝 전/후 동일 질의 비교 문서 작성, 한국어 엔티티 추출 개선 확인.

---

## M4 — (옵션) 완전 로컬 전환 & 문서화

### T09 · Ollama 로컬 전환 (비용 0)
- **목표**: `config/settings.ollama.yaml` 작성, API 키 없이 동작.
- **구현**: `ollama pull qwen2.5 / nomic-embed-text`, `api_base: http://localhost:11434/v1`.
- ⚠️ **함정**: Ollama 기본 컨텍스트 2048 → 인덱싱 중 JSON 출력 잘림 발생. `num_ctx`를 12288 이상으로 상향(Modelfile 고정). 이 내용을 README에 기록.
- **Acceptance**: 키 없이 인덱싱+질의 성공, truncation 경고 없이 커뮤니티 리포트 생성.

### T10 · README & 운영 문서
- **목표**: 설치→마운트→전처리→인덱싱→질의 전 과정 문서화. 비용·시간 실측치, 트러블슈팅 포함.
- **Acceptance**: README만으로 새 PC에서 M0~M2 재현 가능.

---

## settings.yaml 핵심 조정 항목
| 항목 | OpenAI(1차) | Ollama(옵션) |
|---|---|---|
| chat model | `gpt-4o-mini` | `qwen2.5` |
| embedding model | `text-embedding-3-small` | `nomic-embed-text` |
| api_base | 기본 | `http://localhost:11434/v1` |
| api_key | `.env`의 `GRAPHRAG_API_KEY` | 임의값(NONE) |
| num_ctx/max_tokens | 모델 기본 | 12288+ (truncation 방지) |

## Definition of Done
- [ ] M0~M2 전부 Acceptance 통과
- [ ] NAS input/ 에 문서 넣고 1커맨드로 인덱싱→백업→질의 왕복
- [ ] README만으로 재현 가능 + 비용·시간 실측 기록
- [ ] `.env`는 git 제외, `.env.example`로 대체
- [ ] (선택) M3 UI 또는 M4 로컬 전환 중 최소 하나
