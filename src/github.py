import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from src.process import fail
from src.process import run_checked
from src.types import PullRequestData

PR_FIELDS = "number,title,body,baseRefName,headRefName,headRefOid,files"


def get_current_pr(repo_root: Path, pr_url: str | None) -> PullRequestData:
    command = ["gh", "pr", "view"]
    if pr_url:
        command.append(pr_url)
    command.extend(["--json", PR_FIELDS])
    result = run_checked(
        command,
        cwd=repo_root,
        capture_output=True,
    )
    try:
        return cast(PullRequestData, json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        fail(f"failed to parse gh pr view output as JSON: {exc}")


def write_supporting_files(
    tmp_dir: Path, pr_data: PullRequestData, repo_root: Path, pr_url: str | None
) -> tuple[Path, Path, Path]:
    pr_json_path = tmp_dir / "pr.json"
    review_pr_data: dict[str, Any] = {
        "title": pr_data["title"],
        "body": pr_data["body"],
        "baseRefName": pr_data["baseRefName"],
        "headRefName": pr_data["headRefName"],
        "files": pr_data["files"],
    }
    _ = pr_json_path.write_text(
        json.dumps(review_pr_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pr_number = pr_data["number"]
    pr_selector = pr_url or str(pr_number)
    diff_result = run_checked(
        ["gh", "pr", "diff", pr_selector],
        cwd=repo_root,
        capture_output=True,
    )
    pr_diff_path = tmp_dir / "pr.diff"
    _ = pr_diff_path.write_text(diff_result.stdout, encoding="utf-8")

    changed_files_path = tmp_dir / "changed-files.txt"
    changed_files = [item.get("path", "") for item in pr_data["files"]]
    _ = changed_files_path.write_text(
        "\n".join(path for path in changed_files if path)
        + ("\n" if changed_files else ""),
        encoding="utf-8",
    )

    return pr_json_path, changed_files_path, pr_diff_path


def normalize_github_repo_url(url: str) -> str:
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@github.com:"):
        return "https://github.com/" + url.removeprefix("git@github.com:")
    return url


def parse_github_pr_url(pr_url: str) -> tuple[str, int]:
    parsed = urlparse(pr_url)
    if parsed.netloc.lower() != "github.com":
        fail(f"unsupported PR URL host: {parsed.netloc}")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 4 or parts[2] != "pull":
        fail(f"invalid GitHub PR URL: {pr_url}")

    repo_slug = f"{parts[0]}/{parts[1]}"
    try:
        pr_number = int(parts[3])
    except ValueError:
        fail(f"invalid GitHub PR number in URL: {pr_url}")
    return repo_slug, pr_number


def repo_url_from_slug(repo_slug: str) -> str:
    return f"https://github.com/{repo_slug}"


def get_repo_url(repo_root: Path, pr_url: str | None) -> str:
    if pr_url:
        repo_slug, _ = parse_github_pr_url(pr_url)
        return repo_url_from_slug(repo_slug)

    result = run_checked(
        ["gh", "repo", "view", "--json", "url"],
        cwd=repo_root,
        capture_output=True,
    )
    try:
        data = cast(dict[str, Any], json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        fail(f"failed to parse gh repo view output as JSON: {exc}")
    raw_url = data.get("url")
    if not isinstance(raw_url, str) or not raw_url:
        fail("could not determine GitHub repository URL")
    return normalize_github_repo_url(raw_url)


def get_repo_slug(repo_root: Path, pr_url: str | None) -> str:
    if pr_url:
        repo_slug, _ = parse_github_pr_url(pr_url)
        return repo_slug

    result = run_checked(
        ["gh", "repo", "view", "--json", "nameWithOwner"],
        cwd=repo_root,
        capture_output=True,
    )
    try:
        data = cast(dict[str, Any], json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        fail(f"failed to parse gh repo view output as JSON: {exc}")
    name_with_owner = data.get("nameWithOwner")
    if isinstance(name_with_owner, str) and name_with_owner:
        return name_with_owner

    repo_url = get_repo_url(repo_root, pr_url=None).rstrip("/")
    marker = "github.com/"
    if marker not in repo_url:
        fail(f"could not parse GitHub repository slug from URL: {repo_url}")
    return repo_url.split(marker, 1)[1]


def publish_review_comment(
    repo_root: Path,
    *,
    repo_slug: str,
    pr_number: int,
    body: str,
    edit_last: bool,
) -> None:
    command = ["gh", "pr", "comment", str(pr_number), "--repo", repo_slug]
    if edit_last:
        command.extend(["--edit-last", "--create-if-none"])
    command.extend(["--body", body])
    run_checked(command, cwd=repo_root)


def publish_summary_comment(
    repo_root: Path, *, repo_slug: str, pr_number: int, review_body: str
) -> None:
    if review_body.strip() == "NO_FINDINGS":
        body = (
            "<!-- open-warden-review -->\n# AI code review\n\nЗамечаний не найдено.\n"
        )
    else:
        body = (
            "<!-- open-warden-review -->\n"
            "# AI code review\n\n"
            f"{review_body.strip()}\n"
        )
    publish_review_comment(
        repo_root,
        repo_slug=repo_slug,
        pr_number=pr_number,
        body=body,
        edit_last=True,
    )


def publish_ci_review_comment(
    repo_root: Path,
    pr_data: PullRequestData,
    review_body: str,
    pr_url: str | None,
) -> None:
    from src.opencode_runner import looks_like_tool_error

    if looks_like_tool_error(review_body):
        fail("OpenCode returned an error instead of a review; not publishing comments")
    repo_slug = get_repo_slug(repo_root, pr_url)
    publish_summary_comment(
        repo_root,
        repo_slug=repo_slug,
        pr_number=pr_data["number"],
        review_body=review_body,
    )
