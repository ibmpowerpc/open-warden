import os
import subprocess
import sys
from pathlib import Path

from src.config import get_opencode_attempts
from src.prompts import build_candidate_message
from src.prompts import build_selection_message
from src.prompts import clean_review_output
from src.prompts import validate_final_review_output
from src.types import PullRequestData
from src.types import ReviewToolError


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
    print(
        "Starting OpenCode review pass 1/2: collect candidate findings.",
        file=sys.stderr,
    )
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

    print(
        "Starting OpenCode review pass 2/2: select strongest findings.", file=sys.stderr
    )
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
