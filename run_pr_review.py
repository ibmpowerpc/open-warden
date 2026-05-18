#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, NoReturn, TypedDict, cast


DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_CONFIG = "config.toml"
PR_FIELDS = "number,title,body,baseRefName,headRefName,files"


class PullRequestFile(TypedDict, total=False):
    path: str


class PullRequestData(TypedDict):
    number: int
    title: str
    body: str
    baseRefName: str
    headRefName: str
    files: list[PullRequestFile]


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


def get_current_pr(repo_root: Path) -> PullRequestData:
    result = run_checked(
        ["gh", "pr", "view", "--json", PR_FIELDS],
        cwd=repo_root,
        capture_output=True,
    )
    try:
        return cast(PullRequestData, json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        fail(f"failed to parse gh pr view output as JSON: {exc}")


def write_supporting_files(
    tmp_dir: Path, pr_data: PullRequestData, repo_root: Path
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
    diff_result = run_checked(
        ["gh", "pr", "diff", str(pr_number)],
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
    model_id: str,
    model_name: str,
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


def run_opencode(
    repo_root: Path,
    config_path: Path,
    pr_number: int,
    provider_id: str,
    model_id: str,
    attachments: list[Path],
    message: str,
) -> int:
    env = os.environ.copy()
    env["OPENCODE_CONFIG"] = str(config_path)

    cmd = [
        "opencode",
        "run",
        "--model",
        f"{provider_id}/{model_id}",
        "--title",
        f"PR Review #{pr_number}",
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
    )
    return completed.returncode


def main() -> int:
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
    model_id = os.environ.get("OPENCODE_REVIEW_MODEL") or config_str(
        model, "id", default=DEFAULT_MODEL
    )
    model_name = config_str(model, "name", default=model_id)

    if not os.environ.get(api_key_env):
        fail(f"{api_key_env} is not set")

    repo_root = get_repo_root()
    prompt = load_prompt(script_dir, config)
    pr_data = get_current_pr(repo_root)

    scratch_dir = Path(config_str(paths, "scratch_dir", default="tmp/opencode"))
    scratch_root = scratch_dir if scratch_dir.is_absolute() else repo_root / scratch_dir
    scratch_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pr-review.", dir=scratch_root) as tmp_name:
        tmp_dir = Path(tmp_name)
        pr_json_path, changed_files_path, pr_diff_path = write_supporting_files(
            tmp_dir,
            pr_data,
            repo_root,
        )
        config_path = build_opencode_config(
            tmp_dir,
            provider_id=provider_id,
            provider_name=provider_name,
            provider_npm=provider_npm,
            base_url=base_url,
            api_key_env=api_key_env,
            model_id=model_id,
            model_name=model_name,
        )
        message = build_message(pr_data, prompt)
        return run_opencode(
            repo_root,
            config_path,
            pr_data["number"],
            provider_id,
            model_id,
            [pr_json_path, changed_files_path, pr_diff_path],
            message,
        )


if __name__ == "__main__":
    raise SystemExit(main())
