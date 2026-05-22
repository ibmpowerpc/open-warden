from pathlib import Path
from typing import Any

from src.config import config_str
from src.config import get_section
from src.process import fail
from src.types import PullRequestData


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
