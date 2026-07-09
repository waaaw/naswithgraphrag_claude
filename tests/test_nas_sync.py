from pathlib import Path

import pytest

import nas_sync

_DUMMY_ENV = {
    "NAS_HOST": "dummy-host",
    "NAS_SHARE": "dummy-share",
    "NAS_USERNAME": "dummy-user",
    "NAS_PASSWORD": "dummy-pass",
}


def _set_dummy_env(monkeypatch):
    for k, v in _DUMMY_ENV.items():
        monkeypatch.setenv(k, v)


def test_load_nas_config_missing_vars_raises(tmp_path, monkeypatch):
    for k in nas_sync.REQUIRED_ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    # load_nas_config()가 REPO_ROOT/.env를 읽는데, 실제 저장소의 .env에는 진짜
    # NAS 자격증명이 들어있어 delenv만으로는 재현이 안 된다 — 존재하지 않는
    # 경로를 가리키게 해 load_dotenv가 아무 것도 못 읽게 만든다.
    monkeypatch.setattr(nas_sync, "REPO_ROOT", tmp_path)
    with pytest.raises(nas_sync.NasSyncError, match="NAS 접속 정보가"):
        nas_sync.load_nas_config()


def test_load_nas_config_reads_optional_paths_with_defaults(monkeypatch):
    _set_dummy_env(monkeypatch)
    monkeypatch.delenv("NAS_INPUT_PATH", raising=False)
    monkeypatch.delenv("NAS_ARTIFACTS_PATH", raising=False)
    cfg = nas_sync.load_nas_config()
    assert cfg["input_path"] == "input"
    assert cfg["artifacts_path"] == "artifacts"


def test_push_blocks_on_missing_local_output(tmp_path, monkeypatch):
    _set_dummy_env(monkeypatch)
    with pytest.raises(nas_sync.NasSyncError, match="로컬 출력 경로가 없습니다"):
        nas_sync.push(tmp_path / "does_not_exist")


def test_push_blocks_on_incomplete_output(tmp_path, monkeypatch):
    """push는 미러링이라, 핵심 산출물이 빠진 채로 실행하면 NAS의 정상 백업을
    지워버릴 수 있다 — 네트워크 시도 전에 로컬 파일부터 검증해야 한다."""
    _set_dummy_env(monkeypatch)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "entities.parquet").write_bytes(b"dummy")
    # relationships.parquet 등 나머지 필수 파일은 일부러 만들지 않음
    with pytest.raises(nas_sync.NasSyncError, match="핵심 산출물이 없습니다"):
        nas_sync.push(output_dir)


def test_push_passes_file_check_and_mirrors_when_complete(tmp_path, monkeypatch):
    """필수 파일이 모두 있으면 로컬 검증을 통과해 실제 복사 단계(_robocopy)까지
    진행하고, 이때 mirror=True로 호출되는지 확인한다. 실제 네트워크는 스텁으로 대체."""
    _set_dummy_env(monkeypatch)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    for name in nas_sync.REQUIRED_OUTPUT_FILES:
        (output_dir / name).write_bytes(b"dummy")

    calls = {}

    def fake_robocopy(src, dst, mirror=False):
        calls["src"] = src
        calls["dst"] = dst
        calls["mirror"] = mirror

    monkeypatch.setattr(nas_sync.platform, "system", lambda: "Windows")
    monkeypatch.setattr(nas_sync, "_windows_ensure_connection", lambda cfg: "\\\\fake\\share")
    monkeypatch.setattr(nas_sync, "_robocopy", fake_robocopy)

    nas_sync.push(output_dir)

    assert calls["mirror"] is True
    assert calls["src"] == output_dir


def test_robocopy_uses_mirror_flag_only_when_requested(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(nas_sync.subprocess, "run", fake_run)

    # _robocopy는 dst.mkdir()을 실제로 호출하므로 tmp_path 안에서만 다룬다.
    src = tmp_path / "src"
    dst = tmp_path / "dst"

    nas_sync._robocopy(src, dst, mirror=False)
    assert "/MIR" not in captured["cmd"]
    assert "/E" in captured["cmd"]

    nas_sync._robocopy(src, dst, mirror=True)
    assert "/MIR" in captured["cmd"]
    assert "/E" not in captured["cmd"]
