from pathlib import Path

import pytest

import src.opencode_runner as runner


def test_looks_like_tool_error_detects_known_errors() -> None:
    assert runner.looks_like_tool_error("Error: JSON parsing failed")
    assert runner.looks_like_tool_error("permission requested: external_directory")
    assert runner.looks_like_tool_error("Read file failed [offset=1]")
    assert not runner.looks_like_tool_error('{"findings": []}')


def test_run_opencode_with_retries_returns_second_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_run_opencode(*args: object, **kwargs: object) -> int | str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "Error: JSON parsing failed"
        return '{"findings": []}'

    monkeypatch.setattr(runner, "get_opencode_attempts", lambda: 2)
    monkeypatch.setattr(runner, "run_opencode", fake_run_opencode)

    result = runner.run_opencode_with_retries(
        tmp_path,
        tmp_path / "config.json",
        1,
        "provider",
        "model",
        [],
        "message",
        title_suffix=" test",
    )

    assert result == '{"findings": []}'
    assert calls == 2


def test_run_opencode_with_retries_returns_last_tool_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner, "get_opencode_attempts", lambda: 2)
    monkeypatch.setattr(
        runner,
        "run_opencode",
        lambda *args, **kwargs: "Error: JSON parsing failed",
    )

    result = runner.run_opencode_with_retries(
        tmp_path,
        tmp_path / "config.json",
        1,
        "provider",
        "model",
        [],
        "message",
        title_suffix=" test",
    )

    assert result == "Error: JSON parsing failed"


def test_run_opencode_with_retries_does_not_retry_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_run_opencode(*args: object, **kwargs: object) -> int | str:
        nonlocal calls
        calls += 1
        return 2

    monkeypatch.setattr(runner, "get_opencode_attempts", lambda: 3)
    monkeypatch.setattr(runner, "run_opencode", fake_run_opencode)

    result = runner.run_opencode_with_retries(
        tmp_path,
        tmp_path / "config.json",
        1,
        "provider",
        "model",
        [],
        "message",
        title_suffix=" test",
    )

    assert result == 2
    assert calls == 1
