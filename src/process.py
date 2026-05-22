import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


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
    return Path(__file__).resolve().parent.parent
