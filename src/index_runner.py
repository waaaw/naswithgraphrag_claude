#!/usr/bin/env python3
"""GraphRAG 인덱싱 래퍼 (T05).

graphrag index를 실행해 소요시간·토큰 사용량을 로그로 남기고,
완료 후 자동으로 nas_sync.push()를 호출해 결과를 NAS에 백업한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import nas_sync

logger = logging.getLogger("index_runner")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAGPROJ_ROOT = REPO_ROOT / "ragproj"

_METRICS_RE = re.compile(r"Metrics for ([^\n:]+): (\{[^{}]*\})", re.DOTALL)
_LOG_ENCODING = "cp949" if sys.platform == "win32" else "utf-8"


class IndexRunnerError(RuntimeError):
    """인덱싱 중 발생한, 사용자가 원인을 알 수 있는 명확한 오류."""


def _log_offset(log_path: Path) -> int:
    return log_path.stat().st_size if log_path.exists() else 0


def _read_new_log_text(log_path: Path, offset: int) -> str:
    if not log_path.exists():
        return ""
    return log_path.read_bytes()[offset:].decode(_LOG_ENCODING, errors="replace")


def summarize_token_usage(log_text: str) -> dict[str, dict[str, int]]:
    """'Metrics for <model>: {...}' 블록에서 모델별 토큰 사용량을 추출한다."""
    totals: dict[str, dict[str, int]] = {}
    for model, raw_json in _METRICS_RE.findall(log_text):
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        totals[model.strip()] = {
            "attempted_request_count": data.get("attempted_request_count", 0),
            "prompt_tokens": data.get("prompt_tokens", 0),
            "completion_tokens": data.get("completion_tokens", 0),
            "total_tokens": data.get("total_tokens", 0),
        }
    return totals


def run_graphrag_index(root: Path, update: bool) -> tuple[float, dict[str, dict[str, int]]]:
    if not (root / "settings.yaml").exists():
        raise IndexRunnerError(
            f"settings.yaml이 없습니다: {root}. 먼저 'graphrag init --root {root}'를 실행하세요."
        )
    # 주의: `graphrag index --method standard-update`는 실제로는 증분모드를
    # 켜지 않는 CLI 동작이 있어(is_update_run이 항상 False로 하드코딩됨),
    # 증분 인덱싱은 반드시 별도의 `graphrag update` 서브커맨드를 사용해야 한다.
    subcommand = "update" if update else "index"
    log_path = root / "logs" / "indexing-engine.log"
    offset = _log_offset(log_path)

    logger.info("인덱싱 시작: root=%s, subcommand=%s", root, subcommand)
    start = time.time()
    result = subprocess.run(
        ["graphrag", subcommand, "--root", str(root), "--method", "standard"]
    )
    elapsed = time.time() - start

    if result.returncode != 0:
        raise IndexRunnerError(f"graphrag index 실패 (exit={result.returncode})")

    token_usage = summarize_token_usage(_read_new_log_text(log_path, offset))

    logger.info("인덱싱 완료: %.2f초 소요", elapsed)
    if token_usage:
        for model, usage in token_usage.items():
            logger.info(
                "  - %s: 요청 %d회, prompt=%d, completion=%d, total=%d tokens",
                model,
                usage["attempted_request_count"],
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
            )
    else:
        logger.warning("토큰 사용량 로그를 찾지 못했습니다 (%s 확인 필요)", log_path)

    return elapsed, token_usage


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="GraphRAG 인덱싱 실행 + NAS 자동 백업")
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_RAGPROJ_ROOT,
        help="graphrag 프로젝트 루트 (기본 ragproj)",
    )
    parser.add_argument("--update", action="store_true", help="증분 인덱싱(standard-update) 사용")
    parser.add_argument("--no-push", action="store_true", help="완료 후 NAS 백업(push)을 건너뜀")
    args = parser.parse_args()

    try:
        run_graphrag_index(args.root, args.update)
        if not args.no_push:
            logger.info("NAS 백업(push) 시작: %s", args.root / "output")
            nas_sync.push(args.root / "output")
            logger.info("NAS 백업 완료")
    except (IndexRunnerError, nas_sync.NasSyncError) as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
