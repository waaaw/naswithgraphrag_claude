# T08 — 한국어 프롬프트 튜닝 전/후 비교

## 실행 명령

```bash
graphrag prompt-tune --root ./ragproj --language Korean --domain "기술문서" --selection-method all
```

- 소요시간: 31.1초
- 토큰 사용량(gpt-4o-mini): 요청 7회, prompt 29,182 + completion 2,512 = **31,694 tokens**
- 생성된 프롬프트: `extract_graph.txt`, `summarize_descriptions.txt`, `community_report_graph.txt` (3종)

> **CLI 버그 메모**: `--output`의 기본값(`prompts`)은 문서상 "project root 기준 상대경로"라고 되어 있으나,
> 실제로는 **명령을 실행한 현재 작업 디렉터리** 기준으로 해석되어 `D:\Develop\naswithgraphrag_claude\prompts\`
> (저장소 루트, `ragproj` 바깥)에 잘못 생성되었다. `ragproj/prompts/`로 수동 이동 후 정리함.
> (`graphrag index --method standard-update`가 실제로는 증분모드를 켜지 않는 T05의 이슈와 유사한 종류의
> CLI 옵션 처리 버그로 보인다.)

이후 튜닝된 3개 프롬프트를 `ragproj/prompts/`에 반영하고, `graphrag index --root ./ragproj`로 전체
재인덱싱(59.6초)을 수행했다. 튜닝 전 프롬프트는 `ragproj/prompts_before_tuning/`에 백업되어 있다.

## 비교 대상 문서

동일한 샘플 문서 [ragproj/input/smoke_test_sample.txt](../ragproj/input/smoke_test_sample.txt)
(한국어 기술 보고서, 6.2KB)를 튜닝 전/후 동일하게 사용.

## 1. 엔티티 추출 품질

| 항목 | 튜닝 전 (기본 영문 프롬프트) | 튜닝 후 (한국어+기술문서 도메인) |
|---|---|---|
| 총 엔티티 수 | 28 | 20 |
| 총 관계 수 | (기록 없음) | 20 |
| 인물/조직명 언어 | **혼재** (예: `KIM SEO-YEON`, `PARK DO-HYUN`, `아리아 로보틱스`, `김서연`이 동시에 존재) | **한국어로 통일** (로마자 표기 0건) |
| 동일 개체 중복 | 있음 — 예: `ARIA ROBOTICS` vs `아리아 로보틱스`, `ORION`(EVENT) vs `오리온 프로젝트`(ORGANIZATION) | 크게 감소 (엔티티 수 28→20) |
| 엔티티 타입 | 범용 4종(organization/person/geo/event)만 사용, `ORION`이 EVENT로 분류되는 등 부정확 | 도메인 특화 타입 반영: `PROJECT`, `CERTIFICATION`, `MARKET` 등 (일부 한글 타입 라벨 잔존: `프로젝트`/`사람`/`조직`/`팀`) |

**튜닝 전 엔티티 샘플** (일부):
```
ARIA ROBOTICS          ORGANIZATION
KIM SEO-YEON            PERSON
PARK DO-HYUN             PERSON
ORION                    EVENT
오리온 프로젝트           ORGANIZATION   <- 위 ORION과 동일 개체가 중복 추출됨
김서연                    PERSON        <- 위 KIM SEO-YEON과 동일 인물
```

**튜닝 후 엔티티 샘플** (일부):
```
아리아 로보틱스           ORGANIZATION
오리온                    PROJECT
김서연                    PERSON
박도현                    PERSON
ISO 3691-4               CERTIFICATION
전국 물류센터              MARKET
```

**결론**: 가장 뚜렷한 개선은 **엔티티 이름의 언어 일관성**이다. 튜닝 전에는 동일 인물/조직이
로마자 표기와 한글 표기로 이중 추출되어 그래프가 분절되는 문제가 있었으나, 튜닝 후에는 전량
한국어로 통일되어 엔티티 중복이 28→20건으로 감소했다. 다만 일부 커뮤니티 리포트 단계에서
엔티티 타입 라벨 자체가 영문/한글로 혼용되는(`PERSON` vs `사람`) 잔여 이슈는 남아있다.

## 2. 질의 응답 비교

### Global search: "이 문서들의 공통 주제는?"

- **튜닝 전** (해당 세션 T06 실행 결과): 답변 본문 중 인물 나열 부분에
  `"Kim Seo-Yeon, Han Ji-Min, Park Do-Hyun, Jeong Tae-Seok 등 다양한 인물들의 역할을 설명하며..."`
  처럼, 한국어 문장 속에 **로마자 인명이 그대로 섞여** 가독성이 떨어짐.
- **튜닝 후** ([전체 답변](_after_global_answer.txt)): "기술 개발 및 전략적 목표", "팀워크와 리더십의
  중요성", "기술적 요소와 성공 요인", "결론" 4개 섹션으로 더 세분화되었고, 전체 문장이 한국어로
  일관되게 작성됨. (요청 2회, 3,106 tokens, 5.5초)

### Local search: "오리온 프로젝트 기술 리드는 누구야?"

- **튜닝 전**: "오리온 프로젝트의 기술 리드는 **박도현**입니다..." — 정답은 맞았음.
- **튜닝 후** ([전체 답변](_after_local_answer.txt)): "오리온 프로젝트의 기술 리드는 박도현입니다.
  그는 아리아 로보틱스의 수석 엔지니어로서..." — 동일하게 정답이며, 근거 인용이
  `[Data: Reports (1); Entities (3); Relationships (1)]`로 더 구체적으로 제시됨.

## 종합 결론

한국어 도메인 프롬프트 튜닝(`--language Korean --domain "기술문서"`)은 최종 답변의 정답률 자체보다
**지식그래프 엔티티 추출의 언어 일관성과 중복 제거**에서 뚜렷한 개선을 보였다. 소량(6.2KB) 샘플
기준으로는 두 케이스 모두 이미 정답을 반환했지만, 문서량이 늘어나 엔티티 중복이 누적될수록
로마자/한글 혼용으로 인한 그래프 분절 문제가 검색 품질에 더 큰 영향을 줄 것으로 예상되며,
튜닝된 프롬프트가 이를 예방한다.

## 비용/시간 요약

| 단계 | 소요시간 | 토큰 |
|---|---|---|
| `graphrag prompt-tune` | 31.1초 | 31,694 |
| 전체 재인덱싱 (`graphrag index`) | 59.6초 | (인덱싱 로그 참고) |
| Global 질의(튜닝 후) | 5.5초 | 3,106 |
| Local 질의(튜닝 후) | 1.0초 | 22 |
