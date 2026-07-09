import pytest

import backend_switch


@pytest.fixture
def isolated_ragproj(tmp_path, monkeypatch):
    """실제 저장소의 ragproj/를 건드리지 않도록, 백엔드 상태를 저장하는 경로
    상수만 임시 디렉터리로 바꾼다. config/settings.*.yaml은 실제 파일을 읽는다
    (읽기 전용이라 안전하고, 진짜 설정 파일과의 정합성도 함께 검증된다)."""
    ragproj = tmp_path / "ragproj"
    monkeypatch.setattr(backend_switch, "RAGPROJ_ROOT", ragproj)
    monkeypatch.setattr(backend_switch, "BACKEND_MARKER", ragproj / ".backend")
    return ragproj


def test_current_backend_none_when_no_marker(isolated_ragproj):
    assert backend_switch.current_backend() is None


def test_switch_backend_rejects_unknown_value(isolated_ragproj):
    with pytest.raises(backend_switch.BackendSwitchError, match="지원하지 않는"):
        backend_switch.switch_backend("foobar")
    # 실패한 전환은 마커를 남기면 안 된다
    assert backend_switch.current_backend() is None


def test_switch_backend_writes_settings_and_marker(isolated_ragproj):
    backend_switch.switch_backend("openai")
    assert (isolated_ragproj / "settings.yaml").exists()
    assert backend_switch.current_backend() == "openai"


def test_switch_backend_no_warning_on_first_switch(isolated_ragproj, caplog):
    with caplog.at_level("WARNING"):
        backend_switch.switch_backend("openai")
    assert caplog.text == ""


def test_switch_backend_no_warning_when_no_artifacts(isolated_ragproj, caplog):
    backend_switch.switch_backend("openai")
    with caplog.at_level("WARNING"):
        backend_switch.switch_backend("ollama")
    assert caplog.text == ""


def test_switch_backend_warns_when_output_exists(isolated_ragproj, caplog):
    backend_switch.switch_backend("openai")
    (isolated_ragproj / "output").mkdir()
    with caplog.at_level("WARNING"):
        backend_switch.switch_backend("ollama")
    assert "재인덱싱" in caplog.text


def test_switch_backend_warns_when_only_cache_exists(isolated_ragproj, caplog):
    """output은 없어도 cache만 남아있으면(인덱싱 도중 실패 등) 이전 백엔드의
    LLM 응답이 재사용될 수 있으므로 경고가 떠야 한다."""
    backend_switch.switch_backend("openai")
    (isolated_ragproj / "cache").mkdir()
    with caplog.at_level("WARNING"):
        backend_switch.switch_backend("ollama")
    assert "재인덱싱" in caplog.text


def test_switch_backend_no_warning_when_switching_to_same_backend(isolated_ragproj, caplog):
    backend_switch.switch_backend("openai")
    (isolated_ragproj / "output").mkdir()
    with caplog.at_level("WARNING"):
        backend_switch.switch_backend("openai")
    assert caplog.text == ""
