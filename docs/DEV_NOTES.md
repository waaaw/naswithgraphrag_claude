# 개발 노트

이 문서는 이 리포를 처음 맡는 개발자를 위한 기술 노트다. **왜** 이렇게 만들었는지, **무엇을**
직접 겪어서 알게 됐는지를 남긴다. "무엇을 하는 프로젝트인가"는 [MANUAL.md](MANUAL.md), "어떻게
실행하는가"는 [README.md](../README.md)를 참고하고, 여기서는 구현 결정과 함정만 다룬다.

## 1. 아키텍처 결정 배경

**GraphRAG를 직접 감싸는 얇은 CLI 래퍼로 구성한 이유.** LangChain 같은 상위 프레임워크를 얹지
않은 건 의도적인 선택이다. GraphRAG 자체가 엔티티/관계 추출, 커뮤니티 탐지, global/local/drift
검색까지 제공하는 독립 라이브러리라 그 위에 또 다른 추상화를 얹으면 얻는 게 없고, 오히려
`§3`에서 다루는 것 같은 CLI 버그를 추적하기 어려워진다. 실제로 이번 개발 중 `graphrag index
--method standard-update`가 증분모드를 켜지 않는 버그를 `graphrag_llm`/`graphrag` 패키지
소스(`.venv/Lib/site-packages/graphrag/cli/index.py`)까지 직접 읽어서 찾아냈는데, 이게 가능했던
건 우리 코드와 graphrag API 사이에 다른 레이어가 없었기 때문이다.

**NAS는 저장 전용, 연산은 PC.** ipTIME NAS2dual은 ARM 기반 저전력 기기라 LLM 호출이나 임베딩
연산에 적합하지 않다. `src/nas_sync.py`가 파일 복사만 담당하고, 그래프 인덱싱은 전부 개발 PC
(`src/index_runner.py`)에서 수행한다.

**venv, conda 아님.** `CLAUDE.md`에 명시된 규칙. graphrag의 의존성(litellm, lancedb, pyarrow 등)이
conda 채널과 자주 충돌하는 경험 때문에 pip+venv로 고정했다.

## 2. 모듈별 구현 노트

### `src/nas_sync.py`

- OS별로 완전히 다른 백엔드를 쓴다: Windows는 `net use` + `robocopy`([_windows_ensure_connection](../src/nas_sync.py):58, [_robocopy](../src/nas_sync.py):78), Linux는 `mount.cifs` + `rsync`([_linux_mount_and_sync](../src/nas_sync.py):93). 매번 `net use`/`mount`를 시도하고 실패와 무관하게 최종적으로 **경로가 실제 접근 가능한지**(`Path.exists()`)로 성공을 판단한다. `net use`의 리턴코드만으로는 "이미 연결됨"과 "인증 실패"를 구분하기 까다로워서 택한 전략.
- `_windows_ensure_connection`은 비밀번호를 커맨드라인 인자로 넘기지 않고 **표준입력**으로 전달한다(`input=cfg["password"] + "\n"`). 처음엔 `["net", "use", unc_root, password, f"/user:{username}"]`처럼 인자로 넘겼는데, 로컬에서라도 `tasklist /v` 등으로 프로세스 인자가 잠깐 노출될 수 있어 코드 리뷰 때 고쳤다. `PowerShell`의 `Get-SmbMapping`/`Remove-SmbMapping`으로 캐시된 연결을 완전히 지운 클린 상태에서 재인증까지 확인함.
- `_robocopy`의 재시도 값(`/R:5 /W:3`)은 실전에서 정한 값이다. 인덱싱 직후 `ragproj/output/lancedb/`를 NAS로 push하면 **lancedb가 아주 짧게 파일 핸들을 붙잡고 있어** 간헐적으로 실패했다(robocopy exit=9, 디렉터리 1개만 실패). 재시도를 늘려도 여전히 실패하는 경우가 있어서, `src/index_runner.py`의 [_push_with_retry](../src/index_runner.py):127에 push 실패 시 3초 대기 후 1회 더 재시도하는 상위 레벨 재시도를 추가로 얹었다. robocopy 내부 재시도만으로는 이 레이스 컨디션을 항상 못 잡는다.
- robocopy 종료 코드는 0-7이 성공(변경 없음/복사됨 등 조합), 8 이상이 실패라는 점에 유의. `>=8`로 체크한다([_robocopy](../src/nas_sync.py):82).

### `src/preprocess.py`

- `convert_directory`가 같은 stem, 다른 확장자 파일(`report.pdf` + `report.docx`)을 처리할 때
  둘 다 `report.txt`를 만들려고 해서 **하나가 조용히 덮어써지는** 버그가 있었다. 코드 리뷰 때
  발견해서 충돌 시 `report__pdf.txt`처럼 확장자를 붙여 구분하도록 고쳤다([convert_directory](../src/preprocess.py):87). `sorted(input_dir.iterdir())` 순서로 처리되므로 알파벳상 먼저 오는 확장자가 원래 이름을 가져간다는 점을 테스트에 그대로 반영해뒀다(`tests/test_preprocess.py::test_convert_directory_disambiguates_same_stem`).
- `.hwp`는 명시적으로 경고 후 스킵하지만, 처음엔 그 외 미지원 확장자(`.xlsx`, `.pptx` 등)는
  **아무 경고 없이 조용히 무시**됐다. 실제로 NAS에 `.xlsx` 파일이 섞여 들어왔을 때 이걸 몰라서
  수동으로 조사해야 했던 경험 때문에, 모든 미지원 확장자에 경고를 남기도록 고쳤다.
- `extract_docx_text`는 원래 `document.paragraphs`만 읽어서 **표(table) 안의 텍스트를 놓쳤다**.
  표가 많은 문서에서 조용한 데이터 손실이 될 수 있어 `document.tables`도 순회해 `" | "`로 이어
  붙이도록 추가함(문단과 표의 원래 순서는 보존하지 않는 단순화이며, 필요해지면
  `document.element.body`를 순회하는 방식으로 바꿔야 한다).
- pypdf `extract_text()`는 스캔된(이미지) PDF에서 빈 문자열을 반환할 수 있다. OCR은 이 프로젝트
  범위 밖이라, 대신 추출 결과가 비어 있으면 경고 로그만 남긴다.

### `src/index_runner.py`

- **가장 중요한 함정**: `graphrag index --method standard-update`는 CLI가 옵션 값으로는
  받아주지만 실제로는 증분 인덱싱을 켜지 않는다. `graphrag/cli/main.py`의 `_index_cli`가
  `index_cli(..., is_update_run=False)`를 **하드코딩**해서 호출하고, `method` 문자열에
  `-update`가 들어있는지는 보지 않는다. 진짜 증분 인덱싱은 별도 서브커맨드
  `graphrag update --method standard`로만 가능하다(`graphrag/cli/index.py`의 `update_cli`가
  `is_update_run=True`로 호출). [run_graphrag_index](../src/index_runner.py):64가 `--update` 플래그에 따라 `index`/`update` 서브커맨드 자체를 바꾸는 이유다.
- 토큰 사용량은 `ragproj/logs/indexing-engine.log`에서 `Metrics for <model>: {...}` 블록을
  파싱해서 뽑는다. 처음엔 정규식으로 `\{[^{}]*\}`를 매칭했는데, 이건 JSON이 **중첩되면 첫 `}`에서
  잘려버리는** 취약점이 있었다(지금 로그 포맷은 평평해서 문제없었지만 graphrag가 포맷을 바꾸면
  조용히 깨질 뻔했다). `json.JSONDecoder().raw_decode()`로 콜론 뒤 위치부터 파싱하도록 바꿔서
  중첩 깊이에 무관하게 만들었다([summarize_token_usage](../src/index_runner.py):43).
- 로그 파일은 매 실행 전 크기(`_log_offset`)를 기록해두고, 실행 후 그 오프셋 이후 바이트만
  읽어서(`_read_new_log_text`) "이번 실행에서 새로 추가된 로그"만 파싱한다. graphrag가 로그
  파일을 append 방식으로 쓴다는 전제이며, 여러 번의 실행에서 실제로 검증됨. 만약 graphrag가
  버전업하면서 로그 파일을 truncate하는 방식으로 바뀌면 이 오프셋 로직이 깨진다는 점은
  기억해둘 것.
- Windows 콘솔 인코딩 문제(§4) 때문에 로그 파일은 `cp949`로 디코드한다
  (`_LOG_ENCODING = "cp949" if sys.platform == "win32" else "utf-8"`). graphrag가 로그를 쓸 때
  Windows 기본 코드페이지를 따르기 때문.

### `src/query_cli.py`

- `graphrag.cli.query`의 `run_global_search`/`run_local_search`/`run_drift_search`를 **직접
  임포트해서 호출**한다(subprocess로 `graphrag query`를 부르지 않음). 이 함수들은 내부적으로
  `print(response)`를 호출하는데, 그 출력을 파싱해서 재사용하는 대신 함수의 **리턴값**(순수
  Python 문자열)을 그대로 쓴다. 이게 §4에서 다루는 인코딩 문제를 피하는 핵심 트릭이다.
- `--method` 검증과 빈 질문(`--q ""`) 검증을 `run_query()` 안에서 하는 이유: `src/app.py`도 이
  함수를 그대로 import해서 재사용하기 때문에, 검증 로직이 CLI와 UI 양쪽에 동시에 적용된다.
  검증을 `main()`에만 넣으면 app.py 쪽엔 적용이 안 된다.

### `src/app.py`

- Streamlit 자동화 테스트 중 발견한 특이사항(향후 UI 테스트/디버깅 시 참고): `st.text_area`는
  값이 바뀌어도 **Ctrl+Enter를 누르거나 포커스를 잃어야** 세션 상태에 실제로 커밋된다. Playwright
  `fill()`로 DOM 값만 바꾸고 바로 버튼을 누르면 이전(빈) 값으로 스크립트가 재실행된다. 사람이
  쓸 때는 자연스럽게 발생하는 동작이라 문제 없지만, 자동화 스크립트를 짤 때는 `fill` 이후
  Ctrl+Enter에 해당하는 키 이벤트를 명시적으로 보내야 한다.

## 3. graphrag 라이브러리에서 발견한 CLI 버그 정리

이 프로젝트가 쓰는 `graphrag` (PyPI, 3.x)에서 실제로 겪은 버그 두 가지. 업스트림에 픽스가
반영되면 이 리포의 우회 코드도 재검토할 것.

| 증상 | 원인 | 우회 방법 |
|---|---|---|
| `graphrag index --method standard-update`가 매번 전체 재인덱싱처럼 동작 | `graphrag/cli/main.py`의 `_index_cli`가 `is_update_run=False`를 하드코딩 | `graphrag update --method standard` 서브커맨드 사용 |
| `graphrag prompt-tune --output`(기본값 `prompts`)이 `--root`가 아니라 **cwd** 기준으로 해석 | CLI 옵션 파싱 시 root 기준 상대경로 처리 누락으로 추정 | `ragproj` 안에서 실행하거나, 실행 후 생성된 `prompts/`를 `ragproj/prompts/`로 수동 이동 |

## 4. Windows 콘솔 인코딩 (cp949 vs UTF-8)

**증상**: 한글 답변을 콘솔에 출력하면 깨진 문자로 보인다.

**원인**: Windows 한국어 로캘 콘솔의 기본 코드페이지가 cp949라, Python `print()`가 콘솔에 쓸 때
이 코드페이지로 인코딩한다. `sys.stdout.reconfigure(encoding="utf-8")`로 고치려 시도했지만
효과가 없었다 — graphrag가 임포트하는 `colorama`/`rich` 계열 라이브러리가 ANSI 컬러 처리를 위해
`sys.stdout`을 자체 래퍼로 다시 감싸버려서, 우리가 설정한 인코딩이 무시된다.

**우회**: 실제 데이터(파이썬 문자열)는 항상 정상 UTF-8이다. 깨지는 건 콘솔 **표시**뿐이다.
`src/query_cli.py`의 `main()`은 graphrag의 내부 `print()`와 별개로, 응답 문자열을
`sys.stdout.buffer.write(text.encode("utf-8"))`로 **원시 바이트를 직접** 써서 이 래핑 레이어를
완전히 우회한다. 파일로 리다이렉트해서 열면(또는 `Read` 도구 등 UTF-8 인식 뷰어로 보면) 항상
정상적으로 보인다. 이 프로젝트 개발 중에는 답변을 파일로 저장한 뒤 마커 문자열
(`"--- 답변 (UTF-8) ---"`)로 위치를 찾아 UTF-8로 디코드하는 방식으로 검증했다.

## 5. 보안 노트

- `.env`, `ragproj/.env`, `ragproj/output/`, `.venv/`는 모두 `.gitignore` 처리됨.
- NAS 비밀번호는 §2 `nas_sync.py` 항목대로 커맨드라인 인자 대신 표준입력으로 전달.
- 사용자가 NAS에서 직접 받아온 파일(예: `제시모어.xlsx`)은 저장소에 커밋하지 않는다.
  `ragproj/input_excluded/`처럼 인덱싱 대상에서 제외한 사용자 데이터 폴더도
  `.gitignore`에 추가돼 있다.
- OpenAI API 키(`GRAPHRAG_API_KEY`)는 `.env`에서만 읽는다. 코드/설정 파일에 하드코딩된 적 없음.

## 6. 알려진 제한사항 / 향후 개선 아이디어

- **xlsx(스프레드시트) 미지원**: 순수 숫자/표 데이터는 GraphRAG의 엔티티 추출 방식과 안 맞아서
  일부러 구현하지 않았다. 필요해지면 행 단위로 서술형 문장을 생성해 변환하는 방식을 검토할 것
  (`docs/MANUAL.md` §4 참고).
- **docx 표-문단 순서 미보존**: `extract_docx_text`가 문단을 전부 읽은 뒤 표를 이어붙이는
  방식이라, 원본에서 표가 문단 사이에 끼어 있어도 텍스트에서는 뒤로 밀린다. 문서 구조가
  중요해지면 `document.element.body`를 순회해 원래 순서를 보존하도록 바꿔야 한다.
  (`src/preprocess.py`)
- **Ollama 로컬 모드는 설정만 준비됨**: `config/settings.ollama.yaml`과
  `ollama/Modelfile.qwen2.5-ctx12k`는 만들어뒀지만, 실제 Ollama 설치·모델 다운로드·인덱싱
  Acceptance 검증은 사용자 환경에서 직접 해야 한다(수 GB 다운로드가 필요해 자동화 범위 밖).
- **`_log_offset`/`_read_new_log_text`는 append 전제**: §2 `index_runner.py` 항목 참고. graphrag
  로깅 방식이 바뀌면 재검토 필요.

## 7. 디버깅 가이드

- **NAS 연결 문제**: `python src/nas_sync.py --pull`이 실패하면 에러 메시지에 원인이 나온다.
  더 깊이 보려면 `nas_sync.load_nas_config()` / `nas_sync._windows_ensure_connection()`을
  파이썬 REPL에서 직접 호출해보면 어느 단계(설정 로드/인증/경로 접근)에서 막히는지 알 수 있다.
- **인덱싱 실패**: `ragproj/logs/indexing-engine.log`, `ragproj/logs/prompt-tuning.log`를 먼저
  본다. `index_runner.py`는 `graphrag index`/`update`의 stdout/stderr를 그대로 콘솔에
  흘려보내므로(캡처하지 않음), 실패 시 콘솔 출력 자체가 1차 단서다.
- **토큰/비용이 이상하게 보임**: `summarize_token_usage()`가 로그에서 못 찾으면
  "토큰 사용량 로그를 찾지 못했습니다" 경고를 남긴다 — 로그 파일 경로/오프셋을 의심할 것.
- **robocopy 실패 원인을 자세히 보고 싶을 때**: `nas_sync._robocopy()`는 `/NFL /NDL`로 파일별
  로그를 생략한다. 진단이 필요하면 이 두 플래그를 빼고 직접 `subprocess.run`을 호출해보면
  어떤 파일/디렉터리가 실패했는지 나온다(이번 개발 중 lancedb 잠금 문제를 이렇게 찾았다).
