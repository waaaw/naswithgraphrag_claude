import pytest

import query_cli


def test_run_query_rejects_empty_query(tmp_path):
    with pytest.raises(query_cli.QueryCliError, match="비어"):
        query_cli.run_query(tmp_path, "global", "   ")


def test_run_query_rejects_invalid_method(tmp_path):
    (tmp_path / "settings.yaml").write_text("dummy", encoding="utf-8")
    with pytest.raises(query_cli.QueryCliError, match="지원하지 않는 --method"):
        query_cli.run_query(tmp_path, "bogus", "질문")


def test_run_query_requires_settings_yaml(tmp_path):
    with pytest.raises(query_cli.QueryCliError, match="settings.yaml이 없습니다"):
        query_cli.run_query(tmp_path, "global", "질문")


def test_run_query_blocks_on_backend_mismatch(tmp_path, monkeypatch):
    """OpenAI로 인덱싱해놓고 재인덱싱 없이 ollama로 전환한 상태에서 질의하면
    임베딩 비호환으로 이어질 수 있으므로, graphrag를 호출하기 전에 막아야 한다."""
    (tmp_path / "settings.yaml").write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / ".indexed_backend").write_text("openai", encoding="utf-8")
    monkeypatch.setattr(query_cli.backend_switch, "current_backend", lambda: "ollama")

    with pytest.raises(query_cli.QueryCliError, match="openai"):
        query_cli.run_query(tmp_path, "local", "질문")


def test_run_query_allows_matching_backend(tmp_path, monkeypatch):
    (tmp_path / "settings.yaml").write_text("dummy", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / ".indexed_backend").write_text("openai", encoding="utf-8")
    monkeypatch.setattr(query_cli.backend_switch, "current_backend", lambda: "openai")
    monkeypatch.setattr(
        "graphrag.cli.query.run_local_search", lambda **kwargs: ("더미 답변", {})
    )

    result = query_cli.run_query(tmp_path, "local", "질문")
    assert result == "더미 답변"


def test_run_query_skips_check_when_no_marker(tmp_path, monkeypatch):
    """.indexed_backend 마커가 없는 산출물(이 기능 도입 전 결과 등)은 비교 없이
    통과해야 한다 — 소급 적용해서 막으면 기존 사용자를 불필요하게 차단하게 된다."""
    (tmp_path / "settings.yaml").write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(query_cli.backend_switch, "current_backend", lambda: "ollama")
    monkeypatch.setattr(
        "graphrag.cli.query.run_local_search", lambda **kwargs: ("더미 답변", {})
    )

    result = query_cli.run_query(tmp_path, "local", "질문")
    assert result == "더미 답변"


def test_run_query_warns_on_ollama_global(tmp_path, monkeypatch, caplog):
    (tmp_path / "settings.yaml").write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(query_cli.backend_switch, "current_backend", lambda: "ollama")
    monkeypatch.setattr(
        "graphrag.cli.query.run_global_search",
        lambda dynamic_community_selection, **kwargs: ("더미 답변", {}),
    )

    with caplog.at_level("WARNING"):
        query_cli.run_query(tmp_path, "global", "질문")
    assert "알려진 한계" in caplog.text
