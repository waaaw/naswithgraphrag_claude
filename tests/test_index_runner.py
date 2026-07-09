import json

import pytest

import index_runner
import nas_sync


def test_summarize_token_usage_parses_flat_json():
    log_text = (
        'Metrics for openai/gpt-4o-mini: {"attempted_request_count": 2, '
        '"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}\n'
    )
    result = index_runner.summarize_token_usage(log_text)
    assert result == {
        "openai/gpt-4o-mini": {
            "attempted_request_count": 2,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
    }


def test_summarize_token_usage_parses_nested_json():
    """이전 정규식 기반 파서는 값 안에 중첩된 {}가 있으면 첫 '}'에서 잘렸다.
    JSONDecoder.raw_decode 기반 파서는 중첩 깊이와 무관하게 정확히 끝까지 읽어야 한다."""
    nested = {
        "attempted_request_count": 1,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "extra": {"nested": {"deep": True}},
    }
    log_text = f"Metrics for openai/qwen2.5-ctx12k: {json.dumps(nested, indent=2)}\n다음 줄은 무시되어야 함"
    result = index_runner.summarize_token_usage(log_text)
    assert result["openai/qwen2.5-ctx12k"]["total_tokens"] == 15


def test_summarize_token_usage_handles_multiple_models():
    log_text = (
        'Metrics for openai/gpt-4o-mini: {"total_tokens": 100}\n'
        'Metrics for openai/text-embedding-3-small: {"total_tokens": 20}\n'
    )
    result = index_runner.summarize_token_usage(log_text)
    assert set(result.keys()) == {"openai/gpt-4o-mini", "openai/text-embedding-3-small"}
    assert result["openai/gpt-4o-mini"]["total_tokens"] == 100
    assert result["openai/text-embedding-3-small"]["total_tokens"] == 20


def test_summarize_token_usage_empty_log_returns_empty_dict():
    assert index_runner.summarize_token_usage("") == {}


def test_summarize_token_usage_ignores_malformed_json():
    log_text = "Metrics for openai/broken: {not valid json at all\n"
    assert index_runner.summarize_token_usage(log_text) == {}


def test_summarize_token_usage_defaults_missing_fields_to_zero():
    log_text = 'Metrics for openai/x: {"attempted_request_count": 1}\n'
    result = index_runner.summarize_token_usage(log_text)
    assert result["openai/x"]["prompt_tokens"] == 0
    assert result["openai/x"]["total_tokens"] == 0


def test_write_indexed_backend_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(index_runner.backend_switch, "current_backend", lambda: "openai")
    root = tmp_path / "ragproj"
    (root / "output").mkdir(parents=True)
    index_runner._write_indexed_backend_marker(root)
    marker = root / "output" / ".indexed_backend"
    assert marker.read_text(encoding="utf-8") == "openai"


def test_write_indexed_backend_marker_skips_when_no_active_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(index_runner.backend_switch, "current_backend", lambda: None)
    root = tmp_path / "ragproj"
    (root / "output").mkdir(parents=True)
    index_runner._write_indexed_backend_marker(root)
    assert not (root / "output" / ".indexed_backend").exists()


def test_push_with_retry_succeeds_after_transient_failure(tmp_path, monkeypatch):
    calls = []

    def flaky_push(local_output):
        calls.append(local_output)
        if len(calls) < 2:
            raise nas_sync.NasSyncError("일시적 실패")

    monkeypatch.setattr(index_runner.nas_sync, "push", flaky_push)
    monkeypatch.setattr(index_runner.time, "sleep", lambda seconds: None)

    index_runner._push_with_retry(tmp_path, retries=2, wait_seconds=0)

    assert len(calls) == 2


def test_push_with_retry_raises_after_exhausting_retries(tmp_path, monkeypatch):
    def always_fail(local_output):
        raise nas_sync.NasSyncError("영구 실패")

    monkeypatch.setattr(index_runner.nas_sync, "push", always_fail)
    monkeypatch.setattr(index_runner.time, "sleep", lambda seconds: None)

    with pytest.raises(nas_sync.NasSyncError, match="영구 실패"):
        index_runner._push_with_retry(tmp_path, retries=2, wait_seconds=0)
