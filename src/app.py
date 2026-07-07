#!/usr/bin/env python3
"""GraphRAG Streamlit 질의 UI (T07).

실행: streamlit run src/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query_cli import DEFAULT_RAGPROJ_ROOT, VALID_METHODS, QueryCliError, run_query  # noqa: E402

st.set_page_config(page_title="GraphRAG 질의", page_icon="🔎")
st.title("🔎 GraphRAG 질의")
st.caption(f"인덱스 위치: {DEFAULT_RAGPROJ_ROOT}")

method = st.selectbox("검색 방식", VALID_METHODS, index=0)
query = st.text_area("질문", placeholder="예: 이 문서들의 공통 주제는?")

if st.button("질의 실행", type="primary"):
    if not query.strip():
        st.warning("질문을 입력해주세요.")
    else:
        with st.spinner("답변 생성 중..."):
            try:
                response = run_query(DEFAULT_RAGPROJ_ROOT, method, query.strip())
            except QueryCliError as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"질의 중 오류가 발생했습니다: {e}")
            else:
                st.markdown(response)
