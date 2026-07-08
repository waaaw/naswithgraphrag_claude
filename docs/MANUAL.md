# 내 문서를 스스로 이해하는 개인 지식그래프 RAG 시스템

이 문서는 이 프로젝트를 처음 보는 사람을 위한 설명서다 — 무엇을 위해 만들었고, 어떻게 동작하며,
실제로 무엇을 확인했는지를 다룬다. 설치·명령어 등 실행 위주의 내용은 [README.md](../README.md)를 보고,
이 문서는 "왜/어떻게 동작하는가"에 집중한다.

```
NAS2dual(input/) → [pull] → 전처리(txt 변환) → GraphRAG 인덱싱 → [push] → NAS2dual(artifacts/)
                                                        │
                                                        └→ 질의 (CLI / Streamlit UI)
```

## 1. 왜 이런 걸 만들었나

회사·개인 문서가 여러 파일에 흩어져 있으면, "A 프로젝트 기술 리드가 누구였지?" 같은 질문에 답하려면
파일을 하나씩 열어봐야 한다. 검색창에 키워드를 넣는 방식(단순 검색)은 문서 안에 키워드가 그대로
있을 때만 통한다. 이 프로젝트는 그 대신 문서를 읽고 "누가 무엇을 했고 누구와 관련 있는지" 그래프로
미리 정리해둔 뒤, 그 그래프를 근거로 자연어 질문에 답하게 한다.

저장은 이미 갖고 있는 NAS(ipTIME NAS2dual)에 맡기고, 인덱싱처럼 CPU/LLM 호출이 필요한 무거운 작업만
개발 PC에서 수행한다. NAS는 성능이 낮아 연산에 적합하지 않기 때문이다.

## 2. 핵심 개념 3가지

**① RAG란?** Retrieval-Augmented Generation. LLM이 자기 기억만으로 답하지 않고, 관련 문서를
"먼저 찾아서(Retrieval)" 그 내용을 근거로 답을 "생성(Generation)"하는 방식. 내가 가진 문서에만
있는 사실도 답할 수 있고, 근거를 남길 수 있다는 게 장점이다.

**② 일반 RAG의 한계** 보통의 RAG는 문서를 잘게 쪼개 "의미가 비슷한 조각"을 찾아온다. 그런데
"여러 문서에 걸쳐 흩어진 사실을 종합"하는 질문(예: "전체 문서의 공통 주제는?")에는 약하다 —
비슷한 조각을 모아도 전체 그림이 안 보이기 때문이다.

**③ GraphRAG의 차이** Microsoft의 GraphRAG는 인덱싱 단계에서 LLM으로 문서 속 인물·조직·사건
(엔티티)과 그 관계를 미리 추출해 그래프로 만들고, 관련 있는 것들을 "커뮤니티"로 묶어 요약본까지
미리 만들어둔다. 질문이 오면 이 그래프/커뮤니티 요약을 근거로 답한다.

**④ 검색 방식 3가지**
- `global`: 전체를 아우르는 질문("공통 주제는?")에 적합, 커뮤니티 요약을 종합
- `local`: 특정 인물·개체 중심 질문("A 담당자는 누구?")에 적합, 그래프에서 가까운 이웃을 탐색
- `drift`: 두 방식을 섞어 넓게 시작해 좁혀가는 방식

## 3. 구성 요소

각 스크립트는 `src/` 아래에 있고, 전부 단독 CLI로 실행할 수 있다.

| 파일 | 역할 | 실행 예시 |
|---|---|---|
| `nas_sync.py` | NAS ↔ PC 파일 동기화. Windows는 robocopy, Linux는 mount.cifs+rsync로 자동 분기. | `--pull` / `--push` |
| `preprocess.py` | pdf/docx/txt를 정제된 UTF-8 txt로 변환. hwp·xlsx 등 미지원 형식은 경고 후 건너뜀. | `--input ./docs --output ragproj/input` |
| `index_runner.py` | GraphRAG 인덱싱 실행 + 소요시간·토큰 사용량 기록 + 완료 후 NAS 자동 백업. | `python index_runner.py [--update]` |
| `query_cli.py` | 터미널에서 global/local/drift 질의. | `--method global --q "..."` |
| `app.py` | 같은 질의 기능을 웹 UI로. Streamlit 기반. | `streamlit run src/app.py` |

## 4. 실제 사용 흐름

1. **NAS 공유 폴더에 문서 올리기** — 탐색기에서 `\\NAS_IP\graphrag\input`에 pdf/docx/txt 파일을
   넣는다. 숫자 표 데이터(엑셀)처럼 서사형 텍스트가 아닌 파일은 넣어도 인덱싱 품질에 도움이 안 되니
   제외하는 편이 낫다 — 실제로 이번 세션에서 1938~1940년 주가 데이터 xlsx 파일을 발견하고 이
   이유로 제외했다.
2. **PC로 가져오기** — `python src/nas_sync.py --pull`
3. **전처리 (pdf/docx인 경우)** — `python src/preprocess.py --input ragproj/input --output ragproj/input`
4. **인덱싱** — `python src/index_runner.py` (문서 추가만 했다면 `--update`로 변경분만 빠르게 반영)
5. **질문하기** — CLI(`query_cli.py`) 또는 웹 UI(`streamlit run src/app.py`)

## 5. 실제로 확인한 결과

테스트에는 "아리아 로보틱스"라는 가상 회사의 물류 로봇 "오리온" 프로젝트를 다룬 한국어 기술
보고서(6.2KB)를 사용했다.

> **Q. 이 문서들의 공통 주제는?** (global)
> A. 아리아 로보틱스의 오리온 프로젝트가 물류 자동화 기술의 발전, 팀원 간 협력 및 다양한 기술
> 요소의 융합을 통해 경쟁력을 강화하고자 하는 의지를 나타내고 있다 … `[Data: Reports (2, 1, 0)]`

> **Q. 오리온 프로젝트 기술 리드는 누구야?** (local)
> A. 기술 리드는 **박도현**입니다. 아리아 로보틱스의 수석 엔지니어로서 오리온 로봇의 기술 개발을
> 총괄합니다 … `[Data: Entities (3); Relationships (1)]`

### 한국어 프롬프트 튜닝 전/후

기본 프롬프트(영문)로 인덱싱하면 같은 인물이 `KIM SEO-YEON`과 `김서연`처럼 로마자 표기와 한글
표기로 중복 추출되는 문제가 있었다. `graphrag prompt-tune --language Korean --domain "기술문서"`로
튜닝한 뒤 재인덱싱하니 이 중복이 사라졌다.

| | 튜닝 전 | 튜닝 후 |
|---|---|---|
| 엔티티 수 | 28 | 20 |
| 인명·기관명 표기 | 로마자·한글 혼재 | 한글로 통일 |
| 동일 인물 중복 | 다수 발생 | 대부분 해소 |

## 6. 비용과 시간이 얼마나 드나

같은 6.2KB 샘플 문서 기준 실측치. 1차 LLM은 OpenAI gpt-4o-mini + text-embedding-3-small.

| 작업 | 소요시간 | 토큰 |
|---|---|---|
| 최초 전체 인덱싱 | 73.2초 | 26,369 |
| Global 질의 1회 | 19.3초 | 2,551 |
| 증분 인덱싱(변경 없음) | 11~13초 | 21~30 |
| 한국어 프롬프트 튜닝 | 31.1초 | 31,694 |

토큰 비용은 gpt-4o-mini 기준 매우 낮다(전체 인덱싱 한 번에 몇 센트 수준). API 키 없이 완전 무료로
돌리고 싶다면 `python src/backend_switch.py --backend ollama`로 전환할 수 있다(실측: 인덱싱
35.4분, `local`/`drift` 검색 정상, `global` 검색은 아래 함정 참고).

## 7. 실전에서 만난 함정들

직접 부딪혀서 확인한 것들이라, 남들도 똑같이 겪을 가능성이 높다.

**⚠️ CLI 버그 · 증분 인덱싱** — `graphrag index --method standard-update`는 옵션은 받아들이지만
실제로는 증분모드를 켜지 않는다(내부적으로 `is_update_run`이 코드상 `False`로 고정됨). 증분
인덱싱은 반드시 별도 서브커맨드 `graphrag update --method standard`를 써야 한다.
`index_runner.py --update`가 이를 대신 처리한다.

**⚠️ CLI 버그 · prompt-tune 출력 경로** — `graphrag prompt-tune --output`의 기본값은 `--root`
기준이 아니라 **명령을 실행한 현재 디렉터리** 기준으로 해석된다. `ragproj` 바깥에서 실행하면
프롬프트가 엉뚱한 곳에 생긴다.

**⚠️ Ollama num_ctx 함정 (완전 로컬 전환 시)** — Ollama의 기본 컨텍스트 창은 2048 토큰이라,
GraphRAG의 긴 JSON 추출 출력이 중간에 잘린다(truncation). 반드시 `PARAMETER num_ctx 12288`을 넣은
커스텀 Modelfile로 모델을 다시 만들어야 한다.

**⚠️ [차후 해결 과제] Ollama + global 검색 실패** — `qwen2.5:7b`로 인덱싱과 `local`/`drift`
검색까지는 API 키 없이 정상 동작함을 실제로 확인했다("오리온 프로젝트 기술 리드는 누구야?"에
OpenAI와 동일하게 "박도현" 정답 반환). 하지만 `global` 검색은 GraphRAG가 요구하는 엄격한 JSON
응답 형식을 소형 로컬 모델이 못 지켜 "답변할 수 없음"만 나온다. 지금은 고치지 않고 기록만
해뒀다 — 정확한 global 답변이 필요하면 openai 백엔드를 쓸 것.

**⚠️ NAS 백업 시 파일 잠금** — 인덱싱 직후 lancedb 벡터스토어 파일이 아주 짧게 잠겨 있어, 인덱싱이
끝나자마자 NAS로 백업하면 간헐적으로 실패할 수 있었다. 실패 시 3초 대기 후 1회 자동 재시도하도록
처리했다.

**✓ 보안 · NAS 비밀번호** — Windows `net use`에 비밀번호를 커맨드라인 인자로 넘기면 실행 중 다른
프로세스에서 잠깐 보일 수 있어, 표준입력으로 전달하도록 바꿨다. `.env`는 git에 커밋되지 않는다.

**✓ Windows 콘솔 한글 깨짐** — cp949 코드페이지 콘솔에서 한글 답변이 깨져 보일 수 있지만, 실제
데이터는 항상 정상 UTF-8이다. 표시 문제일 뿐이며, 파일로 저장해서 열면 정상적으로 보인다.

## 8. 자주 쓰는 명령

```bash
# 최초 1회
graphrag init --root ./ragproj --model gpt-4o-mini --embedding text-embedding-3-small

# NAS 동기화
python src/nas_sync.py --pull
python src/nas_sync.py --push

# 문서 전처리
python src/preprocess.py --input <원본폴더> --output ragproj/input

# 인덱싱 (+ 자동 NAS 백업)
python src/index_runner.py            # 전체
python src/index_runner.py --update   # 증분

# 질의
python src/query_cli.py --method global --q "이 문서들의 공통 주제는?"
streamlit run src/app.py
```

## 9. 용어집

- **엔티티(Entity)** — 문서에서 추출한 인물·조직·장소·사건 같은 "개체". 그래프의 노드가 된다.
- **커뮤니티(Community)** — 서로 관계가 밀접한 엔티티들의 묶음. GraphRAG가 이 묶음별로 요약
  리포트를 미리 만들어둔다.
- **인덱싱(Indexing)** — 원본 문서를 읽어 엔티티·관계·커뮤니티 요약까지 만드는 전체 준비 과정.
  LLM 호출이 가장 많이 일어나는 단계.
- **증분 인덱싱** — 문서를 추가/수정했을 때 전체를 다시 만들지 않고 바뀐 부분만 반영하는 방식.
- **프롬프트 튜닝** — 엔티티 추출에 쓰는 LLM 지시문(prompt)을 특정 언어·분야에 맞게 자동으로
  다시 생성하는 기능.
- **UNC 경로** — `\\서버\공유이름` 형식의 Windows 네트워크 경로 표기. NAS 접근에 사용.

---

자세한 설치·환경설정·트러블슈팅 커맨드는 [README.md](../README.md)를, 태스크별 완료 기준은
[SPEC.md](../SPEC.md)를 참고. 이 문서는 실제 개발·테스트 세션에서 확인된 수치와 이슈를 바탕으로
작성됨.
