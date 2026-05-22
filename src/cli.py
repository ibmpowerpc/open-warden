import argparse
import os
import sys
import tempfile
from pathlib import Path

from src.config import build_opencode_config
from src.config import config_str
from src.config import get_model_ids
from src.config import get_section
from src.config import load_config
from src.github import get_current_pr
from src.github import publish_ci_review_comment
from src.github import write_supporting_files
from src.opencode_runner import run_two_pass_review
from src.process import fail
from src.process import get_repo_root
from src.process import get_script_dir
from src.process import require_command
from src.prompts import load_prompt
from src.types import ReviewToolError


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
