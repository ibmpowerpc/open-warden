Сделай ревью текущего GitHub pull request, используя приложенные `pr.json`, `changed-files.txt` и `pr.diff`.

Пиши только на русском языке.

Цель: найти реальные баги, внесённые именно этим PR. Не пиши про стиль, вкусовщину, рефакторинг и общие best practices без конкретного failure mode.

Проверь в первую очередь:
- корректность и регрессии поведения
- data integrity и dangling references
- validation gaps и nullable/empty значения
- frontend/backend mismatch
- rollout/migration/runtime failures
- timeout, retry, rollback, non-JSON/network failure paths
- performance issues только с понятным сценарием деградации

Верни только JSON без markdown, без code fences и без пояснений. Ответ должен соответствовать схеме:

{
  "type": "object",
  "additionalProperties": false,
  "required": ["findings"],
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["severity", "path", "line", "body"],
        "properties": {
          "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
          "path": {"type": "string"},
          "line": {"type": "integer", "minimum": 1},
          "body": {"type": "string"}
        }
      }
    }
  }
}

Правила:
- SEVERITY: CRITICAL, HIGH, MEDIUM или LOW.
- Один finding = один объект.
- `path` должен быть путём файла из diff.
- `line` должен быть одной наиболее близкой строкой из изменённого diff.
- `body` должен быть на русском языке, максимум 80 слов.
- Если точную строку определить нельзя, используй ближайшую изменённую строку в том же файле.
- Если сильных findings нет, верни ровно `{ "findings": [] }`.
