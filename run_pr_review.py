#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, NoReturn, TypedDict, cast


DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_CONFIG = "config.toml"
PR_FIELDS = "number,title,body,baseRefName,headRefName,headRefOid,files"
DEFAULT_OPENCODE_ATTEMPTS = 2


class PullRequestFile(TypedDict, total=False):
    path: str


class PullRequestData(TypedDict):
    number: int
    title: str
    body: str
    baseRefName: str
    headRefName: str
    headRefOid: str
    files: list[PullRequestFile]


class ReviewToolError(RuntimeError):
    pass


def fail(message: str, exit_code: int = 1) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def require_command(name: str, hint: str) -> None:
    if shutil.which(name) is None:
        fail(hint)


def run_checked(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            check=True,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as exc:
        stderr = str(exc.stderr or "")
        if stderr:
            print(stderr.rstrip(), file=sys.stderr)
        fail(f"command failed: {' '.join(args)}", exc.returncode)


def get_repo_root() -> Path:
    result = run_checked(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
    )
    repo_root = result.stdout.strip()
    if not repo_root:
        fail("this command must be run inside a git repository")
    return Path(repo_root)


def get_script_dir() -> Path:
    return Path(__file__).resolve().parent


def load_config(script_dir: Path) -> dict[str, Any]:
    config_path = Path(
        os.environ.get("OPENCODE_REVIEW_CONFIG", str(script_dir / DEFAULT_CONFIG))
    )
    try:
        with config_path.open("rb") as config_file:
            return tomllib.load(config_file)
    except FileNotFoundError:
        fail(f"config file not found: {config_path}")
    except tomllib.TOMLDecodeError as exc:
        fail(f"failed to parse TOML config {config_path}: {exc}")


def get_section(config: dict[str, Any], name: str) -> dict[str, Any]:
    section = config.get(name, {})
    if not isinstance(section, dict):
        fail(f"config section [{name}] must be a table")
    return cast(dict[str, Any], section)


def config_str(
    section: dict[str, Any], key: str, *, default: str | None = None
) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value:
        fail(f"config value must be a non-empty string: {key}")
    return value


def config_str_list(section: dict[str, Any], key: str) -> list[str]:
    value = section.get(key, [])
    if not isinstance(value, list):
        fail(f"config value must be a list of strings: {key}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            fail(f"config value must be a list of non-empty strings: {key}")
        result.append(item)
    return result


def get_model_ids(model_section: dict[str, Any]) -> list[str]:
    primary_model = os.environ.get("OPENCODE_REVIEW_MODEL") or config_str(
        model_section, "id", default=DEFAULT_MODEL
    )
    fallback_models_env = os.environ.get("OPENCODE_REVIEW_FALLBACK_MODELS")
    if fallback_models_env:
        fallback_models = [
            model.strip()
            for model in fallback_models_env.split(",")
            if model.strip()
        ]
    else:
        fallback_models = config_str_list(model_section, "fallback_ids")

    model_ids: list[str] = []
    for model_id in [primary_model, *fallback_models]:
        if model_id not in model_ids:
            model_ids.append(model_id)
    return model_ids


def load_prompt(script_dir: Path, config: dict[str, Any]) -> str:
    paths = get_section(config, "paths")
    prompt_path = Path(config_str(paths, "prompt", default="review-prompt.md"))
    if not prompt_path.is_absolute():
        prompt_path = script_dir / prompt_path
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        fail(f"review prompt not found: {prompt_path}")
    return prompt


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


def build_opencode_config(
    tmp_dir: Path,
    *,
    provider_id: str,
    provider_name: str,
    provider_npm: str,
    base_url: str,
    api_key_env: str,
    models: list[tuple[str, str]],
) -> Path:
    config: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: {
                "npm": provider_npm,
                "name": provider_name,
                "options": {
                    "baseURL": base_url,
                    "apiKey": f"{{env:{api_key_env}}}",
                },
                "models": {
                    model_id: {
                        "name": model_name,
                    }
                    for model_id, model_name in models
                },
            }
        },
    }

    config_path = tmp_dir / "opencode.json"
    _ = config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def build_message(pr_data: PullRequestData, prompt: str) -> str:
    return (
        f"Current pull request:\n"
        f"- Base branch: {pr_data['baseRefName']}\n"
        f"- Head branch: {pr_data['headRefName']}\n\n"
        "Use the attached files as the source of truth:\n"
        "- pr.json\n"
        "- changed-files.txt\n"
        "- pr.diff\n\n"
        "Also inspect the repository files when needed to validate whether a suspected issue is real.\n\n"
        f"{prompt}\n"
    )


def build_candidate_message(pr_data: PullRequestData, prompt: str) -> str:
    return (
        build_message(pr_data, prompt)
        + "\n"
        + "Это первый проход ревью. Не останавливайся после первой проблемы: "
        + "просмотри все изменённые файлы и верни до 12 сильных кандидатов. "
        + "Кандидат всё равно должен быть конкретным багом с понятным failure mode.\n"
    )


def build_selection_message(pr_data: PullRequestData) -> str:
    return (
        f"Current pull request:\n"
        f"- Base branch: {pr_data['baseRefName']}\n"
        f"- Head branch: {pr_data['headRefName']}\n\n"
        "Use the attached files as the source of truth:\n"
        "- pr.json\n"
        "- changed-files.txt\n"
        "- pr.diff\n"
        "- candidate-findings.md\n\n"
        "Ты делаешь второй проход ревью. candidate-findings.md содержит находки первого прохода, "
        "но это не полный список и не источник истины.\n\n"
        "Что нужно сделать:\n"
        "- Заново проверь весь diff и связанные changed files.\n"
        "- Учитывай candidate-findings.md, но не ограничивайся им.\n"
        "- Ищи новые проблемы, которые первый проход мог пропустить.\n"
        "- Объедини найденные на первом и втором проходе проблемы.\n"
        "- Удали false positives, дубликаты, догадки, style/refactoring/best practices без конкретного failure mode.\n"
        "- В финальный ответ оставь максимум 5 самых серьёзных findings.\n"
        "- Приоритет: CRITICAL, HIGH, затем MEDIUM. LOW включай только если нет более серьёзных.\n"
        "- Не добавляй finding, если не можешь объяснить, когда он реально проявится.\n"
        "- Если после повторного анализа нет убедительных багов, верни ровно `NO_FINDINGS`.\n\n"
        "Формат ответа строго markdown, без JSON и без fenced code blocks:\n\n"
        "### [SEVERITY] `path/to/file.py:123`\n"
        "Коротко опиши проблему, когда она проявится и минимальное исправление. Максимум 80 слов.\n\n"
        "Не используй intro, summary, outro, verdict, таблицы или списки.\n"
    )


def clean_review_output(text: str) -> str:
    stripped = text.strip()
    if stripped == "NO_FINDINGS":
        return stripped

    lines = stripped.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("### ["):
            return "\n".join(lines[index:]).strip()
    return stripped


def validate_final_review_output(text: str) -> str:
    cleaned = clean_review_output(text)
    if cleaned == "NO_FINDINGS":
        return cleaned

    if cleaned.startswith("{") or cleaned.startswith("[") or "```" in cleaned:
        fail("final OpenCode review is not markdown findings")
    if "### [" not in cleaned:
        fail("final OpenCode review does not contain markdown findings")
    return cleaned


def run_opencode(
    repo_root: Path,
    config_path: Path,
    pr_number: int,
    provider_id: str,
    model_id: str,
    attachments: list[Path],
    message: str,
    capture_output: bool = False,
    title_suffix: str = "",
) -> int | str:
    env = os.environ.copy()
    env["OPENCODE_CONFIG"] = str(config_path)

    cmd = [
        "opencode",
        "run",
        "--model",
        f"{provider_id}/{model_id}",
        "--title",
        f"PR Review #{pr_number}{title_suffix}",
    ]
    for path in attachments:
        cmd.extend(["--file", str(path)])
    cmd.extend(["--", message])

    print(
        f"Running OpenCode review for PR #{pr_number} with model {model_id}...",
        file=sys.stderr,
    )
    completed = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=capture_output,
    )
    if capture_output:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        if completed.returncode == 0:
            return completed.stdout
    return completed.returncode


def get_opencode_attempts() -> int:
    raw_value = os.environ.get("OPENCODE_REVIEW_ATTEMPTS")
    if raw_value is None:
        return DEFAULT_OPENCODE_ATTEMPTS
    try:
        attempts = int(raw_value)
    except ValueError:
        fail("OPENCODE_REVIEW_ATTEMPTS must be an integer")
    if attempts < 1:
        fail("OPENCODE_REVIEW_ATTEMPTS must be greater than zero")
    return attempts


def run_opencode_with_retries(
    repo_root: Path,
    config_path: Path,
    pr_number: int,
    provider_id: str,
    model_id: str,
    attachments: list[Path],
    message: str,
    *,
    title_suffix: str,
) -> int | str:
    attempts = get_opencode_attempts()
    last_result: int | str = 1
    for attempt in range(1, attempts + 1):
        if attempts > 1:
            print(
                f"OpenCode attempt {attempt}/{attempts} for{title_suffix}.",
                file=sys.stderr,
            )
        last_result = run_opencode(
            repo_root,
            config_path,
            pr_number,
            provider_id,
            model_id,
            attachments,
            message,
            capture_output=True,
            title_suffix=title_suffix,
        )
        if isinstance(last_result, int):
            return last_result
        if not looks_like_tool_error(last_result):
            return last_result
        if attempt < attempts:
            print(
                "OpenCode returned a tool-level error; retrying this pass.",
                file=sys.stderr,
            )
    return last_result


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
        body = "<!-- open-warden-review -->\n# AI code review\n\nЗамечаний не найдено.\n"
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
    if looks_like_tool_error(review_body):
        fail("OpenCode returned an error instead of a review; not publishing comments")
    repo_slug = get_repo_slug(repo_root, pr_url)
    publish_summary_comment(
        repo_root,
        repo_slug=repo_slug,
        pr_number=pr_data["number"],
        review_body=review_body,
    )


def run_two_pass_review(
    *,
    repo_root: Path,
    config_path: Path,
    pr_data: PullRequestData,
    provider_id: str,
    model_id: str,
    attachments: list[Path],
    prompt: str,
    tmp_dir: Path,
) -> int | str:
    print("Starting OpenCode review pass 1/2: collect candidate findings.", file=sys.stderr)
    candidate_result = run_opencode_with_retries(
        repo_root,
        config_path,
        pr_data["number"],
        provider_id,
        model_id,
        attachments,
        build_candidate_message(pr_data, prompt),
        title_suffix=" candidates",
    )
    if isinstance(candidate_result, int):
        return candidate_result
    if looks_like_tool_error(candidate_result):
        raise ReviewToolError("OpenCode returned an error during candidate pass")

    candidate_path = tmp_dir / "candidate-findings.md"
    _ = candidate_path.write_text(
        clean_review_output(candidate_result) + "\n",
        encoding="utf-8",
    )

    print("Starting OpenCode review pass 2/2: select strongest findings.", file=sys.stderr)
    final_result = run_opencode_with_retries(
        repo_root,
        config_path,
        pr_data["number"],
        provider_id,
        model_id,
        [*attachments, candidate_path],
        build_selection_message(pr_data),
        title_suffix=" selection",
    )
    if isinstance(final_result, int):
        return final_result
    if looks_like_tool_error(final_result):
        raise ReviewToolError("OpenCode returned an error during selection pass")

    return validate_final_review_output(final_result)


def looks_like_tool_error(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    error_markers = (
        "Error: JSON parsing failed",
        "JSON Parse error",
        "permission requested:",
        "failed [offset=",
    )
    return any(marker in stripped for marker in error_markers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenCode review for current PR.")
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="publish selected findings as one GitHub PR comment",
    )
    parser.add_argument(
        "--pr-url",
        help="explicit GitHub PR URL. By default uses the PR for the current branch",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_command("opencode", "opencode is not installed or not in PATH")
    require_command(
        "gh", "gh CLI is required to inspect the current GitHub pull request"
    )

    script_dir = get_script_dir()
    config = load_config(script_dir)
    provider = get_section(config, "provider")
    model = get_section(config, "model")
    paths = get_section(config, "paths")

    provider_id = config_str(provider, "id", default="routerai")
    provider_name = config_str(provider, "name", default="RouterAI")
    provider_npm = config_str(provider, "npm", default="@ai-sdk/openai-compatible")
    base_url = config_str(provider, "base_url", default="https://routerai.ru/api/v1")
    api_key_env = config_str(provider, "api_key_env", default="ROUTERAI_API_KEY")
    model_ids = get_model_ids(model)
    primary_model_id = model_ids[0]
    primary_model_name = config_str(model, "name", default=primary_model_id)
    model_configs = [
        (model_id, primary_model_name if model_id == primary_model_id else model_id)
        for model_id in model_ids
    ]

    if not os.environ.get(api_key_env):
        fail(f"{api_key_env} is not set")

    repo_root = get_repo_root()
    prompt = load_prompt(script_dir, config)
    pr_data = get_current_pr(repo_root, args.pr_url)

    scratch_dir = Path(config_str(paths, "scratch_dir", default="tmp/opencode"))
    scratch_root = scratch_dir if scratch_dir.is_absolute() else repo_root / scratch_dir
    scratch_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pr-review.", dir=scratch_root) as tmp_name:
        tmp_dir = Path(tmp_name)
        pr_json_path, changed_files_path, pr_diff_path = write_supporting_files(
            tmp_dir,
            pr_data,
            repo_root,
            args.pr_url,
        )
        config_path = build_opencode_config(
            tmp_dir,
            provider_id=provider_id,
            provider_name=provider_name,
            provider_npm=provider_npm,
            base_url=base_url,
            api_key_env=api_key_env,
            models=model_configs,
        )
        last_tool_error: ReviewToolError | None = None
        review_result: int | str | None = None
        for index, model_id in enumerate(model_ids):
            if index > 0:
                print(
                    f"Falling back to review model {model_id}.",
                    file=sys.stderr,
                )
            try:
                review_result = run_two_pass_review(
                    repo_root=repo_root,
                    config_path=config_path,
                    pr_data=pr_data,
                    provider_id=provider_id,
                    model_id=model_id,
                    attachments=[pr_json_path, changed_files_path, pr_diff_path],
                    prompt=prompt,
                    tmp_dir=tmp_dir,
                )
            except ReviewToolError as exc:
                last_tool_error = exc
                if index < len(model_ids) - 1:
                    print(f"{exc}; trying fallback model.", file=sys.stderr)
                    continue
                fail(str(exc))
            break

        if review_result is None:
            fail(str(last_tool_error or "review did not produce a result"))
        if isinstance(review_result, int):
            return review_result

        print(review_result, end="" if review_result.endswith("\n") else "\n")
        if args.ci_mode:
            publish_ci_review_comment(
                repo_root,
                pr_data,
                review_result,
                args.pr_url,
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
