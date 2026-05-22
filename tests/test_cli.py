from pathlib import Path
from types import SimpleNamespace

import pytest

import src.cli as cli
from src.types import ReviewToolError


def setup_cli_mocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    ci_mode: bool,
    review_results: list[int | str | Exception],
) -> list[str]:
    published: list[str] = []
    monkeypatch.setattr(
        cli, "parse_args", lambda: SimpleNamespace(ci_mode=ci_mode, pr_url=None)
    )
    monkeypatch.setattr(cli, "require_command", lambda name, hint: None)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda script_dir: {
            "provider": {
                "id": "provider",
                "name": "Provider",
                "npm": "npm",
                "base_url": "https://example.com",
                "api_key_env": "API_KEY",
            },
            "model": {"id": "primary", "fallback_ids": ["fallback"]},
            "paths": {"scratch_dir": str(tmp_path), "prompt": "review-prompt.md"},
        },
    )
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.delenv("OPENCODE_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("OPENCODE_REVIEW_FALLBACK_MODELS", raising=False)
    monkeypatch.setattr(cli, "get_script_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "load_prompt", lambda script_dir, config: "prompt")
    monkeypatch.setattr(
        cli,
        "get_current_pr",
        lambda repo_root, pr_url: {
            "number": 1,
            "title": "Title",
            "body": "Body",
            "baseRefName": "main",
            "headRefName": "feature",
            "headRefOid": "abc",
            "files": [],
        },
    )

    def fake_write_supporting_files(
        tmp_dir: Path,
        pr_data: object,
        repo_root: Path,
        pr_url: str | None,
    ) -> tuple[Path, Path, Path]:
        paths = (
            tmp_dir / "pr.json",
            tmp_dir / "changed-files.txt",
            tmp_dir / "pr.diff",
        )
        for path in paths:
            path.write_text("", encoding="utf-8")
        return paths

    monkeypatch.setattr(cli, "write_supporting_files", fake_write_supporting_files)
    monkeypatch.setattr(
        cli, "build_opencode_config", lambda *args, **kwargs: tmp_path / "opencode.json"
    )

    def fake_run_two_pass_review(*args: object, **kwargs: object) -> int | str:
        result = review_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cli, "run_two_pass_review", fake_run_two_pass_review)

    def fake_publish(
        repo_root: Path,
        pr_data: object,
        review_body: str,
        pr_url: str | None,
    ) -> None:
        published.append(review_body)

    monkeypatch.setattr(cli, "publish_ci_review_comment", fake_publish)
    return published


def test_main_prints_review_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published = setup_cli_mocks(
        monkeypatch,
        tmp_path,
        ci_mode=False,
        review_results=["review body"],
    )

    assert cli.main() == 0
    assert "review body" in capsys.readouterr().out
    assert published == []


def test_main_publishes_in_ci_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    published = setup_cli_mocks(
        monkeypatch,
        tmp_path,
        ci_mode=True,
        review_results=["review body"],
    )

    assert cli.main() == 0
    assert published == ["review body"]


def test_main_uses_fallback_model_after_tool_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    published = setup_cli_mocks(
        monkeypatch,
        tmp_path,
        ci_mode=True,
        review_results=[ReviewToolError("broken"), "fallback review"],
    )

    assert cli.main() == 0
    assert published == ["fallback review"]
