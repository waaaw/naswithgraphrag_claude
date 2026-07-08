#!/usr/bin/env python3
"""GraphRAG Streamlit 질의 UI (T07).

실행: streamlit run src/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend_switch  # noqa: E402
from query_cli import DEFAULT_RAGPROJ_ROOT, VALID_METHODS, QueryCliError, run_query  # noqa: E402

BACKENDS = ("openai", "ollama")

st.set_page_config(page_title="GraphRAG 질의", page_icon="🔎")
st.title("🔎 GraphRAG 질의")
st.caption(f"인덱스 위치: {DEFAULT_RAGPROJ_ROOT}")

current = backend_switch.current_backend() or "openai"
backend = st.selectbox(
    "LLM 백엔드", BACKENDS, index=BACKENDS.index(current) if current in BACKENDS else 0,
    help="Ollama는 API 키가 필요 없지만, global 검색은 소형 모델의 JSON 형식 준수 한계로 "
    "실패할 수 있습니다(docs/DEV_NOTES.md 참고).",
)
method = st.selectbox("검색 방식", VALID_METHODS, index=0)
query = st.text_area("질문", placeholder="예: 이 문서들의 공통 주제는?")

if method == "global" and backend == "ollama":
    st.info(
        "⚠️ Ollama + global 검색은 알려진 한계로 '답변할 수 없음'이 나올 수 있습니다. "
        "정확한 답이 필요하면 local/drift를 사용하거나 openai 백엔드를 선택하세요."
    )

if st.button("질의 실행", type="primary"):
    if not query.strip():
        st.warning("질문을 입력해주세요.")
    else:
        with st.spinner("답변 생성 중..."):
            try:
                if backend != current:
                    backend_switch.switch_backend(backend)
                response = run_query(DEFAULT_RAGPROJ_ROOT, method, query.strip())
            except (QueryCliError, backend_switch.BackendSwitchError) as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"질의 중 오류가 발생했습니다: {e}")
            else:
                st.markdown(response)
