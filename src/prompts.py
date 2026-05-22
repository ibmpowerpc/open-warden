import json
from pathlib import Path
from typing import Any

from src.config import config_str
from src.config import get_section
from src.process import fail
from src.types import PullRequestData

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
REVIEW_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "path", "line", "body"],
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": sorted(VALID_SEVERITIES),
                    },
                    "path": {"type": "string"},
                    "line": {"type": "integer", "minimum": 1},
                    "body": {"type": "string"},
                },
            },
        }
    },
}


def review_response_schema_text() -> str:
    return json.dumps(REVIEW_RESPONSE_SCHEMA, ensure_ascii=False, indent=2)


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
        '- Если после повторного анализа нет убедительных багов, верни ровно `{ "findings": [] }`.\n\n'
        "Формат ответа строго JSON, без markdown, без fenced code blocks, без intro, summary, outro или verdict.\n"
        "Ответ должен соответствовать этой JSON-схеме:\n\n"
        f"{review_response_schema_text()}\n"
    )


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        fail("model response does not contain a JSON object")
    return stripped[start : end + 1]


def validate_review_json(text: str) -> dict[str, Any]:
    raw_json = extract_json_object(text)
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        fail(f"model response is not valid JSON: {exc}")

    if not isinstance(payload, dict):
        fail("model JSON response must be an object")

    unexpected_keys = set(payload) - {"findings"}
    if unexpected_keys:
        fail(f"model JSON response contains unexpected keys: {sorted(unexpected_keys)}")

    findings = payload.get("findings")
    if not isinstance(findings, list):
        fail("model JSON response must contain a findings array")

    normalized_findings: list[dict[str, Any]] = []
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            fail(f"finding #{index} must be an object")

        unexpected_finding_keys = set(finding) - {"severity", "path", "line", "body"}
        if unexpected_finding_keys:
            fail(
                f"finding #{index} contains unexpected keys: "
                f"{sorted(unexpected_finding_keys)}"
            )

        severity = finding.get("severity")
        path = finding.get("path")
        line = finding.get("line")
        body = finding.get("body")

        if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
            fail(f"finding #{index} has invalid severity")
        if not isinstance(path, str) or not path:
            fail(f"finding #{index} has invalid path")
        if not isinstance(line, int) or line < 1:
            fail(f"finding #{index} has invalid line")
        if not isinstance(body, str) or not body.strip():
            fail(f"finding #{index} has invalid body")

        normalized_findings.append(
            {
                "severity": severity,
                "path": path,
                "line": line,
                "body": body.strip(),
            }
        )

    return {"findings": normalized_findings}


def review_json_to_markdown(payload: dict[str, Any]) -> str:
    findings = payload["findings"]
    if not findings:
        return "NO_FINDINGS"

    sections: list[str] = []
    for finding in findings:
        sections.append(
            f"### [{finding['severity']}] `{finding['path']}:{finding['line']}`\n"
            f"{finding['body']}"
        )
    return "\n\n".join(sections)


def validate_final_review_output(text: str) -> str:
    return review_json_to_markdown(validate_review_json(text))
