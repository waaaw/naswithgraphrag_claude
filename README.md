# NAS2dual + GraphRAG 개인 지식그래프 RAG 시스템

ipTIME NAS2dual(저장 전용) + 개발 PC(GraphRAG 연산)로 구성된 2-Tier 개인 지식그래프 RAG 시스템.
처음 접한다면 개념·아키텍처·실측 데이터 위주로 정리한 [docs/MANUAL.md](docs/MANUAL.md)부터 읽는 걸
추천한다. 마일스톤/태스크 정의는 [SPEC.md](SPEC.md), 작업 원칙은 [CLAUDE.md](CLAUDE.md) 참고.

```
NAS2dual (//nas/graphrag/input, /artifacts)  ── SMB ──  개발 PC (Python + GraphRAG + LLM)
데이터 흐름: NAS input/ → PC 동기화 → 전처리 → 인덱싱 → 결과 NAS 백업 → 질의는 PC 로컬 인덱스에서
```

## 요구사항

- Python 3.10+ (개발/검증: 3.11.9), `venv` 사용 (conda 미사용)
- OpenAI API 키 (1차 LLM: `gpt-4o-mini` + 임베딩 `text-embedding-3-small`)
- (선택) ipTIME NAS2dual 등 SMB 공유 가능한 NAS
- (선택, M4) [Ollama](https://ollama.com) — 완전 로컬/비용 0 전환 시

## 1. 설치

```bash
git clone https://github.com/waaaw/naswithgraphrag_claude.git
cd naswithgraphrag_claude
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. 환경 설정 (.env)

`.env.example`을 복사해 `.env`를 만들고 실제 값을 채운다. **`.env`는 git에 커밋되지 않는다**
(`.gitignore` 처리됨). API 키·NAS 비밀번호를 코드나 커밋에 직접 넣지 말 것.

```bash
cp .env.example .env
```

| 변수 | 설명 |
|---|---|
| `GRAPHRAG_API_KEY` | OpenAI API 키 (`sk-...`) |
| `NAS_HOST` / `NAS_SHARE` | NAS 주소/공유 이름 (예: `nas` / `graphrag`) |
| `NAS_USERNAME` / `NAS_PASSWORD` | NAS 접속 계정 |
| `NAS_INPUT_PATH` / `NAS_ARTIFACTS_PATH` | 공유 내부 상대 경로 (기본 `input` / `artifacts`) |

## 3. GraphRAG 프로젝트 초기화 (최초 1회)

```bash
graphrag init --root ./ragproj --model gpt-4o-mini --embedding text-embedding-3-small
```

`ragproj/settings.yaml`, `ragproj/.env`(GraphRAG 전용, 여기에도 `GRAPHRAG_API_KEY` 필요),
`ragproj/prompts/`가 생성된다. `ragproj/.env`도 git에서 제외됨.

## 4. NAS 동기화 (T03)

```bash
python src/nas_sync.py --pull   # NAS 원본 -> ragproj/input/
python src/nas_sync.py --push   # ragproj/output/ -> NAS 백업
```

- Windows: `net use` + `robocopy` / Linux: `mount.cifs` + `rsync` 로 OS별 자동 분기.
- NAS가 꺼져 있거나 `.env` 설정이 없으면 원인을 알 수 있는 에러 메시지와 함께 종료(exit 1)한다.

## 5. 문서 전처리 (T04)

```bash
python src/preprocess.py --input <원본문서_디렉터리> --output ragproj/input
```

- 지원: `pdf`(`pypdf`), `docx`(`python-docx`), `txt`. `hwp`는 경고 후 건너뜀.
- 제어문자·중복 공백·과도한 빈 줄을 정리해 파일당 1개의 UTF-8 `.txt`로 저장.
- 검증: `pytest tests/test_preprocess.py`

## 6. 인덱싱 (T05)

```bash
python src/index_runner.py            # 전체 인덱싱 + 완료 후 자동 NAS 백업(push)
python src/index_runner.py --update   # 증분 인덱싱(변경분만)
python src/index_runner.py --no-push  # NAS 백업 생략
```

소요시간과 모델별 토큰 사용량(prompt/completion/total)을 로그로 남긴다.
내부적으로 `graphrag index`(전체) 또는 `graphrag update`(증분)를 호출한다.

> ⚠️ **CLI 주의**: `graphrag index --method standard-update`는 옵션상 존재하지만 실제로는
> 증분모드를 켜지 않는 상위 CLI 버그가 있다(`is_update_run`이 코드상 고정 `False`). 증분
> 인덱싱은 반드시 `graphrag update --root <root> --method standard`를 사용해야 하며,
> `src/index_runner.py --update`가 이를 대신 처리해준다.

## 7. 질의

### CLI (T06)

```bash
python src/query_cli.py --method global --q "이 문서들의 공통 주제는?"
python src/query_cli.py --method local  --q "A프로젝트 담당자는 누구야?"
python src/query_cli.py --method drift  --q "..."
```

`--method` 기본값은 `global`이며, 잘못된 값을 주면 사용 가능한 값을 안내하는 에러를 낸다.

### Streamlit UI (T07)

```bash
streamlit run src/app.py
```

검색 방식 선택 + 질문 입력 + 답변 표시로 구성된 단순한 1페이지 UI.

## 8. 한국어 프롬프트 튜닝 (T08, 선택이지만 권장)

```bash
graphrag prompt-tune --root ./ragproj --language Korean --domain "기술문서"
```

엔티티/관계/커뮤니티 리포트 추출 프롬프트를 한국어 + 도메인 특화로 재생성한다.
실측 전/후 비교는 [docs/T08_prompt_tuning.md](docs/T08_prompt_tuning.md) 참고 — 로마자·한글
혼용 엔티티 중복이 크게 줄고(28→20건), 인명·기관명이 한글로 통일되는 효과를 확인했다.

> ⚠️ **CLI 주의**: `--output`의 기본값(`prompts`)은 `--root` 기준 상대경로가 아니라
> **명령을 실행한 현재 작업 디렉터리** 기준으로 해석된다. `./ragproj`에서 실행하지 않았다면
> 생성된 `prompts/`를 수동으로 `ragproj/prompts/`에 옮겨야 한다.

## 9. (M4, 선택) Ollama로 완전 로컬 전환 — 비용 0 (T09)

API 키 없이 전부 로컬에서 돌리고 싶을 때 사용. 이 저장소에는 **설정 파일과 가이드만
준비**되어 있으며, Ollama 설치·모델 다운로드·실제 인덱싱 검증은 사용자 환경에서 직접
수행해야 한다(수 GB 다운로드가 필요해 이 리포의 자동화 범위에서 제외함).

```bash
# 1) Ollama 설치 후 모델 받기
ollama pull qwen2.5
ollama pull nomic-embed-text

# 2) num_ctx 함정 대응: 커스텀 모델 생성 (아래 설명 참고)
ollama create qwen2.5-ctx12k -f ollama/Modelfile.qwen2.5-ctx12k

# 3) 설정 적용
cp config/settings.ollama.yaml ragproj/settings.yaml

# 4) 인덱싱/질의는 기존과 동일하게 실행 (API 키 불필요)
python src/index_runner.py --no-push
python src/query_cli.py --method global --q "..."
```

### ⚠️ num_ctx 함정

Ollama의 `qwen2.5` 기본 컨텍스트 창은 **2048 토큰**이다. GraphRAG의 엔티티/관계 추출과
커뮤니티 리포트 생성은 이보다 훨씬 긴 JSON 출력을 요구하므로, 기본값 그대로 쓰면
**인덱싱 도중 출력이 잘려(truncation)** 파싱 오류나 불완전한 그래프가 만들어진다.

해결책은 API 호출 시 `num_ctx`를 넘기는 것만으로는 신뢰할 수 없고(경로에 따라 무시될 수
있음), **[ollama/Modelfile.qwen2.5-ctx12k](ollama/Modelfile.qwen2.5-ctx12k)로 컨텍스트를
모델 자체에 고정**해야 한다:

```
FROM qwen2.5
PARAMETER num_ctx 12288
```

[config/settings.ollama.yaml](config/settings.ollama.yaml)은 이 커스텀 모델(`qwen2.5-ctx12k`)을
가리키도록 이미 구성되어 있다. Acceptance 기준(키 없이 인덱싱+질의 성공, truncation
경고 없이 커뮤니티 리포트 생성)은 위 절차대로 Ollama를 설치한 뒤 직접 검증한다.

## 실측 비용·시간 (샘플 문서 6.2KB, 한국어 기술 보고서 기준)

| 단계 | 소요시간 | 토큰 사용량 |
|---|---|---|
| 최초 전체 인덱싱 (`graphrag index`, T02) | 73.2초 | 26,369 (gpt-4o-mini 21,453 + embedding 4,916) |
| Global 질의 1회 | 19.3초 | 2,551 |
| 증분 인덱싱 (`graphrag update`, 변경 없음, T05) | 11~13초 | 21~30 (거의 무료) |
| `graphrag prompt-tune` (T08) | 31.1초 | 31,694 |
| 프롬프트 튜닝 후 전체 재인덱싱 | 59.6초 | (인덱싱 로그 참고) |

모든 소요시간/토큰은 `ragproj/logs/indexing-engine.log`, `ragproj/logs/query.log`,
`ragproj/output/stats.json`에 GraphRAG 자체 계측치로 남는다.

## 트러블슈팅

- **`AuthenticationError: Incorrect API key provided`**: `ragproj/.env`의
  `GRAPHRAG_API_KEY`에 공백/줄바꿈이 섞여 들어갔는지, 키가 만료/폐기되지 않았는지
  [OpenAI 콘솔](https://platform.openai.com/account/api-keys)에서 확인한다.
- **Windows 콘솔(cp949)에서 한글 답변이 깨져 보임**: 실제 데이터는 항상 정상 UTF-8이며
  표시만 깨진다(Windows 콘솔 코드페이지 문제). 파일로 저장해 열거나, `src/query_cli.py`처럼
  `sys.stdout.buffer`에 UTF-8 바이트를 직접 쓰면 우회할 수 있다.
- **`graphrag index --method standard-update`가 증분 인덱싱을 하지 않음**: CLI 버그.
  `graphrag update --root <root> --method standard`를 사용할 것 (`index_runner.py --update`가
  자동 처리).
- **`graphrag prompt-tune`이 엉뚱한 위치에 프롬프트를 생성함**: `--output` 기본값이
  `--root`가 아니라 현재 작업 디렉터리 기준. `ragproj/prompts/`로 수동 이동 필요.
- **NAS 관련 에러**: `python src/nas_sync.py --pull`/`--push`가 NAS 전원/네트워크/자격증명
  문제를 원인과 함께 명확히 알려준다. `.env`의 `NAS_*` 값을 다시 확인.

## 리포지토리 구조

```
naswithgraphrag_claude/
├─ CLAUDE.md / SPEC.md / README.md
├─ requirements.txt / .env.example / .gitignore
├─ config/
│   ├─ settings.openai.yaml     # 1차(OpenAI) 참고 템플릿
│   └─ settings.ollama.yaml     # T09 로컬 전환용
├─ ollama/
│   └─ Modelfile.qwen2.5-ctx12k # T09 num_ctx 고정
├─ src/
│   ├─ nas_sync.py       # T03
│   ├─ preprocess.py     # T04
│   ├─ index_runner.py   # T05
│   ├─ query_cli.py      # T06
│   └─ app.py            # T07
├─ ragproj/
│   ├─ input/ output/ prompts/ ...  # graphrag init/index 산출물
├─ docs/
│   └─ T08_prompt_tuning.md  # 프롬프트 튜닝 전/후 비교
└─ tests/
    └─ test_preprocess.py
```

## Definition of Done

체크리스트는 [SPEC.md](SPEC.md#definition-of-done) 참고.
