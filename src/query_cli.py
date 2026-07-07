#!/usr/bin/env python3
"""GraphRAG CLI 질의 (T06): global/local/drift 선택 질의.

  python src/query_cli.py --method global --q "이 문서들의 공통 주제는?"
  python src/query_cli.py --method local  --q "A프로젝트 담당자는 누구야?"
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger("query_cli")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAGPROJ_ROOT = REPO_ROOT / "ragproj"

VALID_METHODS = ("global", "local", "drift")


class QueryCliError(RuntimeError):
    """질의 중 발생한, 사용자가 원인을 알 수 있는 명확한 오류."""


def run_query(root: Path, method: str, query: str) -> str:
    if method not in VALID_METHODS:
        raise QueryCliError(
            f"지원하지 않는 --method 값입니다: '{method}'. "
            f"다음 중 하나를 사용하세요: {', '.join(VALID_METHODS)}"
        )
    if not (root / "settings.yaml").exists():
        raise QueryCliError(
            f"settings.yaml이 없습니다: {root}. 먼저 인덱싱을 완료하세요 "
            f"(graphrag index 또는 src/index_runner.py)."
        )

    from graphrag.cli.query import run_drift_search, run_global_search, run_local_search

    common_kwargs = {
        "data_dir": None,
        "root_dir": root,
        "community_level": 2,
        "response_type": "Multiple Paragraphs",
        "streaming": False,
        "query": query,
        "verbose": False,
    }

    if method == "global":
        response, _ = run_global_search(dynamic_community_selection=False, **common_kwargs)
    elif method == "local":
        response, _ = run_local_search(**common_kwargs)
    else:  # drift
        response, _ = run_drift_search(**common_kwargs)
    return response


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="GraphRAG 질의 (global/local/drift)")
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_RAGPROJ_ROOT,
        help="graphrag 프로젝트 루트 (기본 ragproj)",
    )
    parser.add_argument("--method", default="global", help="검색 방식: global(기본)/local/drift")
    parser.add_argument("--q", "--query", dest="query", required=True, help="질의 문자열")
    args = parser.parse_args()

    try:
        response = run_query(args.root, args.method, args.query)
    except QueryCliError as e:
        logger.error(str(e))
        sys.exit(1)
        return

    # graphrag 내부에서도 print(response)를 호출하지만, Windows 콘솔 코드페이지
    # (예: cp949) 환경에서는 한글이 깨질 수 있어, 원시 UTF-8 바이트로 한 번 더
    # 명확하게 출력한다.
    sys.stdout.flush()
    sys.stdout.buffer.write(f"\n--- 답변 (UTF-8) ---\n{response}\n".encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
