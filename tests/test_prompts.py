import pytest

from src.prompts import review_json_to_markdown
from src.prompts import review_response_schema_text
from src.prompts import validate_review_json


def test_review_response_schema_text_contains_findings_schema() -> None:
    schema = review_response_schema_text()

    assert '"findings"' in schema
    assert '"additionalProperties": false' in schema


def test_validate_review_json_accepts_empty_findings() -> None:
    assert validate_review_json('{"findings": []}') == {"findings": []}


def test_validate_review_json_accepts_fenced_json() -> None:
    payload = validate_review_json(
        """```json
{"findings":[{"severity":"MEDIUM","path":"src/app.py","line":42,"body":"bug"}]}
```"""
    )

    assert payload == {
        "findings": [
            {
                "severity": "MEDIUM",
                "path": "src/app.py",
                "line": 42,
                "body": "bug",
            }
        ]
    }


def test_validate_review_json_extracts_json_from_surrounding_text() -> None:
    payload = validate_review_json(
        'prefix {"findings":[{"severity":"HIGH","path":"a.py","line":1,"body":"x"}]} suffix'
    )

    assert payload["findings"][0]["severity"] == "HIGH"


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '{"extra": true, "findings": []}',
        '{"findings": "not-a-list"}',
        '{"findings": [{"severity": "INFO", "path": "a.py", "line": 1, "body": "x"}]}',
        '{"findings": [{"severity": "LOW", "path": "", "line": 1, "body": "x"}]}',
        '{"findings": [{"severity": "LOW", "path": "a.py", "line": 0, "body": "x"}]}',
        '{"findings": [{"severity": "LOW", "path": "a.py", "line": 1, "body": ""}]}',
        '{"findings": [{"severity": "LOW", "path": "a.py", "line": 1, "body": "x", "extra": true}]}',
    ],
)
def test_validate_review_json_rejects_invalid_payloads(raw: str) -> None:
    with pytest.raises(SystemExit):
        validate_review_json(raw)


def test_review_json_to_markdown_formats_empty_findings() -> None:
    assert review_json_to_markdown({"findings": []}) == "NO_FINDINGS"


def test_review_json_to_markdown_formats_findings() -> None:
    markdown = review_json_to_markdown(
        {
            "findings": [
                {
                    "severity": "MEDIUM",
                    "path": "file.py",
                    "line": 10,
                    "body": "first",
                },
                {
                    "severity": "HIGH",
                    "path": "other.py",
                    "line": 20,
                    "body": "second",
                },
            ]
        }
    )

    assert markdown == (
        "### [MEDIUM] `file.py:10`\n"
        "first\n\n"
        "### [HIGH] `other.py:20`\n"
        "second"
    )
