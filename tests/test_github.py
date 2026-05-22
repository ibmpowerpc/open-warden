import json
import subprocess
from pathlib import Path

import pytest

import src.github as github


def test_parse_github_pr_url() -> None:
    assert github.parse_github_pr_url("https://github.com/owner/repo/pull/123") == (
        "owner/repo",
        123,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/owner/repo/pull/123",
        "https://github.com/owner/repo/issues/123",
        "https://github.com/owner/repo/pull/not-a-number",
    ],
)
def test_parse_github_pr_url_rejects_invalid_urls(url: str) -> None:
    with pytest.raises(SystemExit):
        github.parse_github_pr_url(url)


def test_write_supporting_files_uses_pr_url_for_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run_checked(
        args: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="diff text")

    monkeypatch.setattr(github, "run_checked", fake_run_checked)
    pr_data: github.PullRequestData = {
        "number": 123,
        "title": "Title",
        "body": "Body",
        "baseRefName": "main",
        "headRefName": "feature",
        "headRefOid": "abc",
        "files": [{"path": "a.py"}, {"path": "b.py"}],
    }

    pr_json_path, changed_files_path, diff_path = github.write_supporting_files(
        tmp_path,
        pr_data,
        tmp_path,
        "https://github.com/owner/repo/pull/123",
    )

    assert calls == [["gh", "pr", "diff", "https://github.com/owner/repo/pull/123"]]
    assert json.loads(pr_json_path.read_text(encoding="utf-8"))["title"] == "Title"
    assert changed_files_path.read_text(encoding="utf-8") == "a.py\nb.py\n"
    assert diff_path.read_text(encoding="utf-8") == "diff text"


def test_write_supporting_files_uses_pr_number_without_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run_checked(
        args: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="diff text")

    monkeypatch.setattr(github, "run_checked", fake_run_checked)
    pr_data: github.PullRequestData = {
        "number": 123,
        "title": "Title",
        "body": "Body",
        "baseRefName": "main",
        "headRefName": "feature",
        "headRefOid": "abc",
        "files": [],
    }

    github.write_supporting_files(tmp_path, pr_data, tmp_path, None)

    assert calls == [["gh", "pr", "diff", "123"]]
