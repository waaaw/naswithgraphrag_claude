#!/usr/bin/env python3
"""NAS <-> PC 동기화 (T03).

--pull: NAS 원본 입력 문서를 로컬 ragproj/input/ 으로 복사
--push: 로컬 ragproj/output/ 인덱싱 결과를 NAS 백업 경로로 **미러링**
        (robocopy /MIR, rsync --delete — NAS 쪽에만 있는 파일도 지운다)

NAS 접속 정보(NAS_HOST/NAS_SHARE/NAS_USERNAME/NAS_PASSWORD)는 반드시
프로젝트 루트 .env 에서 읽는다. 코드에 하드코딩하지 않는다.
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("nas_sync")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_INPUT = REPO_ROOT / "ragproj" / "input"
DEFAULT_LOCAL_OUTPUT = REPO_ROOT / "ragproj" / "output"

REQUIRED_ENV_VARS = ["NAS_HOST", "NAS_SHARE", "NAS_USERNAME", "NAS_PASSWORD"]

# push는 미러링(NAS 쪽에만 있는 파일도 삭제)이라, 로컬 output이 불완전한 상태로
# 실행하면 NAS의 정상 백업까지 지워버릴 수 있다. 최소한 이 핵심 산출물이 있어야
# push를 허용한다.
REQUIRED_OUTPUT_FILES = [
    "entities.parquet",
    "relationships.parquet",
    "communities.parquet",
    "community_reports.parquet",
    "documents.parquet",
    "text_units.parquet",
]


class NasSyncError(RuntimeError):
    """NAS 동기화 중 발생한, 사용자가 원인을 알 수 있는 명확한 오류."""


def load_nas_config() -> dict:
    load_dotenv(REPO_ROOT / ".env")
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        raise NasSyncError(
            f"NAS 접속 정보가 .env에 없습니다: {', '.join(missing)}. "
            f".env.example을 참고해 프로젝트 루트 .env에 값을 채워주세요."
        )
    return {
        "host": os.environ["NAS_HOST"],
        "share": os.environ["NAS_SHARE"],
        "username": os.environ["NAS_USERNAME"],
        "password": os.environ["NAS_PASSWORD"],
        "input_path": os.environ.get("NAS_INPUT_PATH", "input"),
        "artifacts_path": os.environ.get("NAS_ARTIFACTS_PATH", "artifacts"),
    }


def _windows_unc_root(cfg: dict) -> str:
    return f"\\\\{cfg['host']}\\{cfg['share']}"


def _windows_ensure_connection(cfg: dict) -> str:
    unc_root = _windows_unc_root(cfg)
    # net use 실패(이미 연결됨 등)와 무관하게, 최종적으로 경로가 실제
    # 접근 가능한지로 판단한다.
    # 비밀번호를 커맨드라인 인자로 넘기면 실행 중 다른 프로세스에서 잠깐이라도
    # 볼 수 있으므로(tasklist /v 등), 인자에서 빼고 표준입력으로 전달한다.
    subprocess.run(
        ["net", "use", unc_root, f"/user:{cfg['username']}"],
        input=cfg["password"] + "\n",
        capture_output=True,
        text=True,
    )
    if not Path(unc_root).exists():
        raise NasSyncError(
            f"NAS({unc_root})에 접근할 수 없습니다. NAS 전원/네트워크 상태와 "
            f".env의 NAS_HOST/NAS_SHARE/NAS_USERNAME/NAS_PASSWORD 값을 확인하세요."
        )
    return unc_root


def _robocopy(src: Path, dst: Path, mirror: bool = False) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    # /R:5 /W:3: 인덱싱 직후(예: lancedb) 파일 핸들이 잠깐 남아있는 경우가 있어
    # 넉넉한 재시도로 일시적 잠금 실패를 흡수한다.
    # mirror=True(/MIR)는 push 전용이다. lancedb는 append-only 트랜잭션 로그라
    # 단순 복사(/E)만 쓰면 과거 인덱싱의 잔여 파일이 NAS에 영원히 쌓인다.
    # pull에는 절대 쓰지 않는다 — ragproj/input은 preprocess.py가 같은 폴더에
    # 로컬 전용 변환 결과(txt)를 만들어두는데, NAS 원본에는 없는 그 파일들까지
    # /MIR이 지워버릴 수 있기 때문이다.
    copy_flag = "/MIR" if mirror else "/E"
    cmd = ["robocopy", str(src), str(dst), copy_flag, "/R:5", "/W:3", "/NFL", "/NDL"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # robocopy exit code: 0-7 성공(변화 없음/복사됨 등), 8 이상은 실패
    if result.returncode >= 8:
        raise NasSyncError(
            f"robocopy 실패 (exit={result.returncode}): {src} -> {dst}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    logger.info("robocopy 완료: %s -> %s (exit=%s)", src, dst, result.returncode)


def _linux_mount_and_sync(cfg: dict, remote_subpath: str, local_dir: Path, direction: str) -> None:
    mount_point = Path(tempfile.mkdtemp(prefix="nas_graphrag_"))
    cred_fd, cred_path_str = tempfile.mkstemp(prefix="nas_cred_")
    cred_path = Path(cred_path_str)
    try:
        with os.fdopen(cred_fd, "w") as f:
            f.write(f"username={cfg['username']}\npassword={cfg['password']}\n")
        cred_path.chmod(0o600)
        unc = f"//{cfg['host']}/{cfg['share']}"
        result = subprocess.run(
            [
                "sudo", "mount", "-t", "cifs", unc, str(mount_point),
                "-o", f"credentials={cred_path},uid={os.getuid()},gid={os.getgid()}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise NasSyncError(
                f"NAS 마운트 실패: {unc} -> {mount_point}\n{result.stderr.strip()}\n"
                f"NAS 전원/네트워크/자격증명 및 mount.cifs(cifs-utils) 설치 여부를 확인하세요."
            )
        remote_dir = mount_point / remote_subpath
        if direction == "pull":
            if not remote_dir.exists():
                raise NasSyncError(f"NAS 원격 경로가 없습니다: {remote_dir}")
            local_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["rsync", "-av", f"{remote_dir}/", f"{local_dir}/"], check=True)
        else:
            remote_dir.mkdir(parents=True, exist_ok=True)
            # --delete: push는 미러링(Windows push의 robocopy /MIR과 동일 의도).
            # pull에는 절대 쓰지 않는다 — _robocopy의 mirror 주석 참고.
            subprocess.run(["rsync", "-av", "--delete", f"{local_dir}/", f"{remote_dir}/"], check=True)
    finally:
        subprocess.run(["sudo", "umount", str(mount_point)], capture_output=True)
        cred_path.unlink(missing_ok=True)
        try:
            mount_point.rmdir()
        except OSError:
            pass


def pull(local_input: Path = DEFAULT_LOCAL_INPUT) -> None:
    cfg = load_nas_config()
    system = platform.system()
    if system == "Windows":
        unc_root = _windows_ensure_connection(cfg)
        remote_dir = Path(unc_root) / cfg["input_path"]
        if not remote_dir.exists():
            raise NasSyncError(f"NAS 입력 경로가 없습니다: {remote_dir}")
        _robocopy(remote_dir, local_input)
    elif system == "Linux":
        _linux_mount_and_sync(cfg, cfg["input_path"], local_input, "pull")
    else:
        raise NasSyncError(f"지원하지 않는 OS입니다: {system}")
    logger.info("PULL 완료: NAS(%s) -> %s", cfg["input_path"], local_input)


def push(local_output: Path = DEFAULT_LOCAL_OUTPUT) -> None:
    cfg = load_nas_config()
    if not local_output.exists():
        raise NasSyncError(f"로컬 출력 경로가 없습니다: {local_output} (먼저 인덱싱을 실행하세요)")
    missing = [f for f in REQUIRED_OUTPUT_FILES if not (local_output / f).exists()]
    if missing:
        raise NasSyncError(
            f"{local_output}에 핵심 산출물이 없습니다: {', '.join(missing)}. "
            f"push는 미러링이라 NAS 쪽 기존 파일도 지워지므로, 불완전한 상태로 실행하면 "
            f"NAS의 정상 백업까지 삭제될 수 있어 막았습니다. 먼저 전체 인덱싱을 완료하세요."
        )
    system = platform.system()
    if system == "Windows":
        unc_root = _windows_ensure_connection(cfg)
        remote_dir = Path(unc_root) / cfg["artifacts_path"]
        _robocopy(local_output, remote_dir, mirror=True)
    elif system == "Linux":
        _linux_mount_and_sync(cfg, cfg["artifacts_path"], local_output, "push")
    else:
        raise NasSyncError(f"지원하지 않는 OS입니다: {system}")
    logger.info("PUSH 완료: %s -> NAS(%s)", local_output, cfg["artifacts_path"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="NAS <-> PC 동기화 (GraphRAG 입력/결과)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pull", action="store_true", help="NAS 원본 -> 로컬 ragproj/input")
    group.add_argument("--push", action="store_true", help="로컬 ragproj/output -> NAS 백업")
    args = parser.parse_args()

    try:
        if args.pull:
            pull()
        elif args.push:
            push()
    except NasSyncError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
