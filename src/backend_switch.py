#!/usr/bin/env python3
"""LLM 백엔드 전환 (T09): OpenAI <-> Ollama.

config/settings.<backend>.yaml을 ragproj/settings.yaml로 복사해 활성 백엔드를 바꾼다.
서로 다른 백엔드는 임베딩 차원·모델이 달라 산출물이 호환되지 않으므로, 전환 시
기존 ragproj/output/이 있으면 경고만 하고(자동 삭제하지 않음) 재인덱싱을 안내한다.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("backend_switch")

REPO_ROOT = Path(__file__).resolve().parent.parent
RAGPROJ_ROOT = REPO_ROOT / "ragproj"
BACKEND_MARKER = RAGPROJ_ROOT / ".backend"
VALID_BACKENDS = ("openai", "ollama")


class BackendSwitchError(RuntimeError):
    """백엔드 전환 중 발생한, 사용자가 원인을 알 수 있는 명확한 오류."""


def current_backend() -> str | None:
    if BACKEND_MARKER.exists():
        return BACKEND_MARKER.read_text(encoding="utf-8").strip()
    return None


def switch_backend(backend: str) -> None:
    if backend not in VALID_BACKENDS:
        raise BackendSwitchError(
            f"지원하지 않는 --backend 값입니다: '{backend}'. "
            f"다음 중 하나를 사용하세요: {', '.join(VALID_BACKENDS)}"
        )
    src_config = REPO_ROOT / "config" / f"settings.{backend}.yaml"
    if not src_config.exists():
        raise BackendSwitchError(f"설정 파일이 없습니다: {src_config}")

    prev = current_backend()
    output_dir = RAGPROJ_ROOT / "output"
    cache_dir = RAGPROJ_ROOT / "cache"
    # output이 없어도 cache만 남아있으면(예: 인덱싱이 도중에 실패한 경우) 이전 백엔드의
    # LLM 응답이 캐시에 남아 다음 인덱싱에서 재사용될 수 있으므로 cache_dir도 함께 본다.
    if prev is not None and prev != backend and (output_dir.exists() or cache_dir.exists()):
        logger.warning(
            "백엔드를 %s -> %s로 전환합니다. 서로 다른 백엔드의 임베딩/모델은 호환되지 "
            "않으므로, 다음 인덱싱 전에 기존 ragproj/output(및 cache)을 지우고 전체 "
            "재인덱싱하세요. 그렇지 않으면 벡터 차원 불일치 등으로 실패할 수 있습니다.",
            prev, backend,
        )

    RAGPROJ_ROOT.mkdir(parents=True, exist_ok=True)
    dest = RAGPROJ_ROOT / "settings.yaml"
    shutil.copy(src_config, dest)
    BACKEND_MARKER.write_text(backend, encoding="utf-8")
    logger.info("백엔드 전환 완료: %s -> %s", src_config, dest)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="LLM 백엔드 전환 (openai/ollama)")
    parser.add_argument("--backend", required=True, help="openai 또는 ollama")
    args = parser.parse_args()

    try:
        switch_backend(args.backend)
    except BackendSwitchError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
